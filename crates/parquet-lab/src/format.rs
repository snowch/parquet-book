//! The fixed parts of a Parquet file: the magic bytes at each end, and the trailer.
//!
//! ```text
//! offset 0                                                         file_size
//! │                                                                        │
//! ▼                                                                        ▼
//! ┌──────┬─────────────────────────┬──────────────────┬────────────┬──────┐
//! │ PAR1 │ row groups (the data)   │ footer           │ footer len │ PAR1 │
//! │  4   │ …                       │ FileMetaData     │ u32 LE, 4  │  4   │
//! └──────┴─────────────────────────┴──────────────────┴────────────┴──────┘
//!                                                     └──── trailer: 8 ────┘
//! ```
//!
//! A reader starts at the *end*. Nothing at the front of the file says where anything is: the
//! writer did not know the offsets of its row groups until it had written them, so it wrote the
//! map last. The last eight bytes are the only part of the file whose position is known before
//! reading anything, and they say how to find the map.

use std::fmt;

use crate::bytes::{le_terms, read_le_u32, Span};

/// The four ASCII bytes `PAR1` that open and close every unencrypted Parquet file.
pub const MAGIC: [u8; 4] = *b"PAR1";

/// The closing magic of a file whose footer is encrypted (ch13). Recognised, not yet read.
pub const MAGIC_ENCRYPTED_FOOTER: [u8; 4] = *b"PARE";

/// The trailer: a four-byte footer length followed by the four-byte magic.
pub const TRAILER_LEN: u64 = 8;

/// The smallest file that can be valid: opening magic plus trailer, with an empty footer. No
/// real writer produces one, because a `FileMetaData` has required fields, but it is the
/// bound below which a reader can stop without looking.
pub const MIN_FILE_LEN: u64 = MAGIC.len() as u64 + TRAILER_LEN;

/// Why a file could not be located, before any metadata was parsed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FormatError {
    TooShort { file_size: u64 },
    BadMagic { found: [u8; 4], span: Span },
    EncryptedFooter,
    FooterLengthTooLarge { footer_length: u32, available: u64 },
}

impl fmt::Display for FormatError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            FormatError::TooShort { file_size } => write!(
                f,
                "a {file_size}-byte file cannot be Parquet: the magic and trailer alone take {MIN_FILE_LEN}"
            ),
            FormatError::BadMagic { found, span } => write!(
                f,
                "expected PAR1 at {span}, found {:02x} {:02x} {:02x} {:02x}",
                found[0], found[1], found[2], found[3]
            ),
            FormatError::EncryptedFooter => write!(
                f,
                "this file ends in PARE: its footer is encrypted, and without the footer key a reader can see only its crypto metadata (ch13)"
            ),
            FormatError::FooterLengthTooLarge { footer_length, available } => write!(
                f,
                "the trailer claims a {footer_length}-byte footer, but only {available} bytes lie between the opening magic and the trailer"
            ),
        }
    }
}

impl std::error::Error for FormatError {}

/// The last eight bytes of a file, decoded.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Trailer {
    /// The eight raw bytes, as read.
    pub bytes: [u8; 8],
    /// Where they sit in the file: always the last eight bytes.
    pub span: Span,
    /// The first four bytes, read as a little-endian `u32`.
    pub footer_length: u32,
    /// The last four bytes.
    pub magic: [u8; 4],
}

impl Trailer {
    /// The span of the footer-length field alone.
    pub fn length_span(&self) -> Span {
        Span::new(self.span.start, self.span.start + 4)
    }

    /// The span of the closing magic alone.
    pub fn magic_span(&self) -> Span {
        Span::new(self.span.start + 4, self.span.end)
    }

    /// The footer-length bytes with the weight of each, for showing the arithmetic.
    pub fn length_terms(&self) -> Vec<(u8, u64)> {
        le_terms(&self.bytes[..4])
    }
}

/// Decode the trailer of a file of `file_size` bytes from its last eight bytes.
pub fn parse_trailer(last8: [u8; 8], file_size: u64) -> Result<Trailer, FormatError> {
    if file_size < MIN_FILE_LEN {
        return Err(FormatError::TooShort { file_size });
    }
    let span = Span::new(file_size - TRAILER_LEN, file_size);
    let magic = [last8[4], last8[5], last8[6], last8[7]];
    if magic == MAGIC_ENCRYPTED_FOOTER {
        return Err(FormatError::EncryptedFooter);
    }
    if magic != MAGIC {
        return Err(FormatError::BadMagic {
            found: magic,
            span: Span::new(span.start + 4, span.end),
        });
    }
    let footer_length = read_le_u32([last8[0], last8[1], last8[2], last8[3]]);
    Ok(Trailer {
        bytes: last8,
        span,
        footer_length,
        magic,
    })
}

/// Where the footer is: the `footer_length` bytes that end where the trailer begins.
///
/// ```text
/// footer_start = file_size - 8 - footer_length
/// footer_end   = file_size - 8
/// ```
///
/// The footer cannot overlap the opening magic, so a length that would put its start before
/// byte 4 means the trailer is lying, and the reader stops rather than trusting it.
pub fn footer_span(file_size: u64, footer_length: u32) -> Result<Span, FormatError> {
    if file_size < MIN_FILE_LEN {
        return Err(FormatError::TooShort { file_size });
    }
    let footer_end = file_size - TRAILER_LEN;
    let available = footer_end - MAGIC.len() as u64;
    if u64::from(footer_length) > available {
        return Err(FormatError::FooterLengthTooLarge {
            footer_length,
            available,
        });
    }
    Ok(Span::new(footer_end - u64::from(footer_length), footer_end))
}

/// Check the opening magic: the first four bytes of the file.
pub fn check_header(first4: [u8; 4]) -> Result<Span, FormatError> {
    let span = Span::new(0, MAGIC.len() as u64);
    if first4 == MAGIC {
        Ok(span)
    } else {
        Err(FormatError::BadMagic {
            found: first4,
            span,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trailer(len: u32, magic: &[u8; 4]) -> [u8; 8] {
        let l = len.to_le_bytes();
        [
            l[0], l[1], l[2], l[3], magic[0], magic[1], magic[2], magic[3],
        ]
    }

    #[test]
    fn the_trailer_is_a_length_then_the_magic() {
        let t = parse_trailer(trailer(380, b"PAR1"), 637).unwrap();
        assert_eq!(t.footer_length, 380);
        assert_eq!(t.span, Span::new(629, 637));
        assert_eq!(t.length_span(), Span::new(629, 633));
        assert_eq!(t.magic_span(), Span::new(633, 637));
    }

    #[test]
    fn the_footer_ends_where_the_trailer_starts() {
        assert_eq!(footer_span(637, 380).unwrap(), Span::new(249, 629));
    }

    #[test]
    fn a_footer_may_fill_everything_after_the_opening_magic_and_no_more() {
        assert_eq!(footer_span(100, 88).unwrap(), Span::new(4, 92));
        assert_eq!(
            footer_span(100, 89),
            Err(FormatError::FooterLengthTooLarge {
                footer_length: 89,
                available: 88
            })
        );
    }

    #[test]
    fn wrong_magic_is_reported_with_its_position() {
        let err = parse_trailer(trailer(10, b"PAR2"), 64).unwrap_err();
        assert_eq!(
            err,
            FormatError::BadMagic {
                found: *b"PAR2",
                span: Span::new(60, 64)
            }
        );
    }

    #[test]
    fn an_encrypted_footer_is_recognised_rather_than_misread() {
        assert_eq!(
            parse_trailer(trailer(10, b"PARE"), 64),
            Err(FormatError::EncryptedFooter)
        );
    }

    #[test]
    fn a_file_shorter_than_its_fixed_parts_is_refused() {
        assert_eq!(
            parse_trailer(trailer(0, b"PAR1"), 11),
            Err(FormatError::TooShort { file_size: 11 })
        );
        assert!(parse_trailer(trailer(0, b"PAR1"), 12).is_ok());
    }
}
