//! ch13's problems. Edit this file; `exercises/tests/modular_encryption.rs` grades it.

/// Problem 13.1: find the modules of an encrypted column chunk.
///
/// `chunk` is an encrypted column chunk's bytes. It is a run of modules, each a four-byte
/// little-endian length followed by that many bytes (a 12-byte nonce, the ciphertext, a 16-byte
/// tag). Return each module's `(offset, size)` within `chunk`, where `size` counts the length
/// prefix too.
pub fn modules(chunk: &[u8]) -> Vec<(usize, usize)> {
    let _ = chunk;
    todo!("problem 13.1")
}

/// How a file's footer is protected.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FooterMode {
    /// No modular encryption.
    NotEncrypted,
    /// Encrypted columns, and a readable footer signed with the footer key.
    PlaintextFooter,
    /// The footer itself is encrypted.
    EncryptedFooter,
}

/// Problem 13.2: which footer mode does a file use?
///
/// Decide from the file's bytes. You may use the book's reader:
/// `parquet_lab::report::open_bytes(file)` decodes a readable footer, and its
/// `encryption_algorithm` is set when the file uses modular encryption.
pub fn footer_mode(file: &[u8]) -> FooterMode {
    let _ = file;
    todo!("problem 13.2")
}
