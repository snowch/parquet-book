//! Modular encryption: what a reader without keys can still see (ch13).
//!
//! Parquet encrypts a file in **modules**: the footer, and for each encrypted column every page
//! header and every page, separately. Each module is written the same way:
//!
//! ```text
//! [length: u32, little-endian]   the bytes that follow
//! [nonce: 12 bytes]              never reused under one key
//! [ciphertext]                   the module, encrypted with AES
//! [tag: 16 bytes]                AES-GCM's check that nothing was changed
//! ```
//!
//! A file uses one of two footer modes:
//!
//! - **Encrypted footer.** The file starts and ends with `PARE`. The footer is a plaintext
//!   `FileCryptoMetaData`, naming the algorithm and the footer key, followed by the real
//!   `FileMetaData` as one encrypted module. Without the footer key a reader knows nothing of
//!   the schema, the row groups or where any column is.
//! - **Plaintext footer.** The file is `PAR1` throughout, and the footer is readable, followed by
//!   a signature: a nonce and a tag computed with the footer key. A reader without keys sees the
//!   schema and every unencrypted column. Encrypted columns show where they are and how big, and
//!   their pages are modules it cannot open.
//!
//! This module reads everything that is not encrypted, and describes the modules that are. It
//! does not decrypt: that needs AES and the keys, and ch13 is about what remains without them.

use crate::bytes::{ByteReader, Span};
use crate::thrift::{read_struct, Node};

/// The magic an encrypted-footer file starts and ends with.
pub const MAGIC_ENCRYPTED: [u8; 4] = *b"PARE";
pub const NONCE_LEN: u64 = 12;
pub const TAG_LEN: u64 = 16;

/// One encrypted module, split into its parts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Module {
    pub span: Span,
    pub length: Span,
    pub nonce: Span,
    pub ciphertext: Span,
    pub tag: Span,
}

/// Read the module that starts at `r`, from its length prefix alone.
pub fn read_module(r: &mut ByteReader) -> Result<Module, String> {
    let start = r.offset();
    let len = r.read_le_u32().map_err(|e| e.to_string())? as u64;
    if len < NONCE_LEN + TAG_LEN {
        return Err(format!(
            "a module at offset {start} claims {len} bytes, fewer than a nonce and a tag"
        ));
    }
    let (_, body) = r.read_bytes(len as usize).map_err(|e| e.to_string())?;
    Ok(Module {
        span: Span::new(start, body.end),
        length: Span::new(start, start + 4),
        nonce: Span::new(body.start, body.start + NONCE_LEN),
        ciphertext: Span::new(body.start + NONCE_LEN, body.end - TAG_LEN),
        tag: Span::new(body.end - TAG_LEN, body.end),
    })
}

/// The modules of an encrypted column chunk: page headers and pages, alternating.
pub fn chunk_modules(file: &[u8], chunk: Span) -> Result<Vec<Module>, String> {
    let bytes = file
        .get(chunk.start as usize..chunk.end as usize)
        .ok_or(format!("column chunk {chunk} is past the end of the file"))?;
    let mut r = ByteReader::new(bytes, chunk.start);
    let mut out = Vec::new();
    while !r.is_at_end() {
        out.push(read_module(&mut r)?);
    }
    Ok(out)
}

/// What an encrypted-footer file shows: its crypto metadata, and one module where the
/// `FileMetaData` should be.
#[derive(Clone, Debug, PartialEq)]
pub struct EncryptedFooter {
    pub footer: Span,
    pub crypto_metadata: Node,
    pub algorithm: String,
    pub key_metadata: Option<Vec<u8>>,
    pub module: Module,
}

/// Read an encrypted-footer file's footer, as far as anyone without the footer key can.
pub fn encrypted_footer(file: &[u8]) -> Result<EncryptedFooter, String> {
    let size = file.len() as u64;
    if size < 12 || file[..4] != MAGIC_ENCRYPTED || file[file.len() - 4..] != MAGIC_ENCRYPTED {
        return Err("not an encrypted-footer file: it does not start and end with PARE".into());
    }
    let length = u32::from_le_bytes(file[file.len() - 8..file.len() - 4].try_into().unwrap());
    let footer = crate::format::footer_span(size, length).map_err(|e| e.to_string())?;
    let bytes = &file[footer.start as usize..footer.end as usize];
    let mut r = ByteReader::new(bytes, footer.start);
    let crypto_metadata = read_struct(&mut r).map_err(|e| format!("FileCryptoMetaData: {e}"))?;
    let s = crate::metadata::as_struct(&crypto_metadata).map_err(|e| e.to_string())?;
    let algorithm = s
        .field(1)
        .map(|f| crate::metadata::union_member(&f.node))
        .unwrap_or_else(|| "UNKNOWN".into());
    let key_metadata = match s.field(2).map(|f| &f.node.value) {
        Some(crate::thrift::Value::Binary(b)) => Some(b.clone()),
        _ => None,
    };
    let module = read_module(&mut r)?;
    if !r.is_at_end() {
        return Err(format!(
            "{} bytes follow the encrypted FileMetaData inside the footer",
            footer.end - r.offset()
        ));
    }
    Ok(EncryptedFooter {
        footer,
        crypto_metadata,
        algorithm,
        key_metadata,
        module,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_module_is_its_length_then_nonce_ciphertext_and_tag() {
        let mut bytes = (40u32).to_le_bytes().to_vec();
        bytes.extend([7u8; 40]);
        let m = read_module(&mut ByteReader::new(&bytes, 100)).unwrap();
        assert_eq!(m.span, Span::new(100, 144));
        assert_eq!(m.nonce, Span::new(104, 116));
        assert_eq!(m.ciphertext, Span::new(116, 128));
        assert_eq!(m.tag, Span::new(128, 144));
        let short = (20u32).to_le_bytes();
        assert!(read_module(&mut ByteReader::new(&short, 0)).is_err());
    }
}
