---
title: Modular encryption
---

(modular-encryption)=
# Modular encryption

## The question

What can a reader still see in an encrypted file, and what changes for it?

Everything so far assumed a reader could read every byte. Parquet can encrypt a file, and does so
in pieces: the footer, and for each protected column every page header and every page, each
encrypted on its own. A reader with the right keys decrypts what it needs. A reader without them
sees a file whose shape is still visible and whose protected contents are not. This chapter reads
two encrypted files without their keys, and reports exactly where the reader stops.

## The experiment

### Two files, two footer modes

`plaintext-footer.parquet` and `encrypted-footer.parquet` hold the same twelve orders, with the
same keys. `email` is encrypted with one key and `amount_cents` with another; `order_id` and
`country` are not encrypted. The files differ in one choice: whether the footer is encrypted too.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name.

**Footer modes.** A Parquet file starts and ends with its magic, as
[ch02](#anatomy-of-a-parquet-file) found. Read the first and last four bytes of both files:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/modular_encryption/footer_modes.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/footer_modes.rs
:language: rust
```
:::
::::

The plaintext-footer file starts and ends with `PAR1`, like every file so far, and a reader that
knows nothing of encryption opens it as usual. The encrypted-footer file has `PARE` at both ends,
and such a reader refuses it at the magic. Add `"tiny"` to the list of files: it ends with
`PAR1` too, so the magic alone cannot tell a plaintext footer from a file with no encryption at
all. Problem 13.2 asks you to tell the three apart.

### Keys by name

Neither file holds a key. Each encrypted piece carries **key metadata**, which names a key
without revealing it. pyarrow writes it as JSON, so a search of the raw bytes finds it.

**Keys by name.** Find every piece of key metadata in both files, and print the key it names:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/modular_encryption/keys_by_name.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/keys_by_name.rs
:language: rust
```
:::
::::

The plaintext-footer file names three keys in the clear: one for each encrypted column, and one
for the footer. The encrypted-footer file names only the footer key. The columns' key metadata is
still there, inside the footer, and the footer is encrypted. Print all of the JSON: it also
records whether the data key was wrapped once or twice and, for the footer key, which key service
to ask.

The scheme is envelope encryption. Each column is encrypted with a random data key. That data key
is wrapped, encrypted, with a master key that stays inside a key management service: the
`wrappedDEK` the step printed is the wrapped data key. A reader sends it to the service, which
unwraps it only for a reader allowed to have it. Different columns can use different master
keys, so one reader may see `amount_cents` and not `email`.

The fixtures use a toy key service that wraps by XOR with master keys published in
`fixtures/generate.py`. It protects nothing, on purpose: the files exist to show what encryption
hides from a reader without keys, and anyone may regenerate them.

### Modules

Parquet encrypts **modules**, not files. Every encrypted piece is laid out the same way:

```text
[length: u32, little-endian]   the bytes that follow
[nonce: 12 bytes]              never reused under one key
[ciphertext]                   the module, encrypted with AES
[tag: 16 bytes]                AES-GCM's check that nothing was changed
```

**One module.** The plaintext footer still says where `email`'s column chunk is. Read the first
module of the chunk from its length prefix:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/modular_encryption/one_module.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/one_module.rs
:language: rust
```
:::
::::

The footer gives the chunk's place and size, but no statistics: those are in the encrypted copy
of the column's metadata. The module's length counts the nonce, the ciphertext and the tag, and
the next module starts where it ends. Set `at` to that byte and run the step again: the second
module ends exactly where the chunk ends. The first module is the page's header and the second
the page. Change the column to `amount_cents` and read its first module the same way. Walking
every module of a chunk is problem 13.1.

Encrypting each page separately keeps what earlier chapters built. A reader with the keys can
still fetch one page from the middle of a file and decrypt it alone, as [ch10](#how-readers-read)
fetched pages. And a reader without the keys can still find every module, by its length prefix,
the way [ch06](#pages) walked page headers.

The algorithm is **AES-GCM**. It encrypts, and its tag also authenticates: a module changed by a
single bit fails to decrypt instead of decrypting to something wrong. Each module is also bound
to its place in the file, its row group, column and page number, through the data GCM
authenticates alongside the ciphertext, so a module cannot be moved from one place to another
unnoticed. A second algorithm, `AES_GCM_CTR_V1`, authenticates the metadata but encrypts pages
with plain counter mode, which is faster and leaves the pages unauthenticated.

### The file, module by module

The panel lays out both files as the reader parsed them, in the structure and byte views of
[ch02](#anatomy-of-a-parquet-file)'s panel, and lists the columns as a reader without keys finds
them. Select a column's name to mark its bytes.

```lab
experiment: encryption
fixture: plaintext-footer.parquet
fixtures: plaintext-footer.parquet, encrypted-footer.parquet
```

Try these:

1. **Select `email`.** Its chunk is the two modules the step read, a page header and a page. The
   structure view splits each into its length, nonce, ciphertext and tag.
2. **Find the signature.** In the structure view, after the `FileMetaData`, a nonce and a tag
   sign the footer.
3. **Switch to `encrypted-footer.parquet`.** No column can be located. The structure view shows a
   plaintext `FileCryptoMetaData` and one encrypted module where the `FileMetaData` should be.

### What a plaintext footer shows

```{include} _generated/encryption-plaintext-footer.md
```

With a plaintext footer, the file still starts and ends with `PAR1`, and a reader that knows
nothing of encryption reads the unencrypted columns as usual. The encrypted columns keep a
reduced `ColumnMetaData` in the footer: their type, encodings, codec, sizes and offsets, but no
statistics. The full metadata, statistics included, is itself an encrypted module inside the
footer. Readers without keys therefore cannot skip by those columns' statistics, and cannot read
them at all.

The footer ends with a **signature**: a nonce and a GCM tag computed with the footer key. A
reader with that key can check that nobody changed the footer. A reader without it cannot, and
has to trust the footer as it is.

### What an encrypted footer shows

```{include} _generated/encryption-encrypted-footer.md
```

With an encrypted footer, the file starts and ends with `PARE`, and the footer is a small
plaintext `FileCryptoMetaData`, naming the algorithm and the footer key, followed by the real
`FileMetaData` as one module. Even the unencrypted columns cannot be read: their bytes are there
in plain form, but the footer that says where they are is not.

### What still leaks

Encryption hides values, not shape. From the steps, the tables above and the panel, a reader
without keys still learns:

- **the file's size, and in a plaintext footer every column chunk's size and offset;**
- **how many pages each encrypted column has, and how long each is.** AES-GCM does not change a
  module's length, so the ciphertext is exactly as long as the page, and page lengths can say
  something about the values;
- **which columns are protected, and by which named keys.**

The encrypted footer hides more of the shape, at the price of making the whole file unreadable
without the footer key.

## Building it

The steps read the magic, the key metadata and one module by hand, and stopped where a key would
be needed. The reader does the same for every module, in both footer modes, and says where it
stops.

### Walking modules

A module is read from its length prefix alone, as the step read one, and an encrypted column chunk
is a run of them:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/crypto.py
:language: python
:start-at: def read_module(r: ByteReader)
:end-before: def chunk_modules(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/crypto.rs
:language: rust
:start-at: pub fn read_module(
:end-before: /// The modules of an encrypted column chunk
```
:::
::::

### An encrypted footer

A file that ends with `PARE` has a footer in two parts. The reader decodes the first, the
plaintext `FileCryptoMetaData`, for the algorithm and the footer key's metadata, and reads the
rest as one module, which must end where the footer does:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/crypto.py
:language: python
:start-at: def encrypted_footer(file: bytes)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/crypto.rs
:language: rust
:start-at: pub fn encrypted_footer(
:end-before: #[cfg(test)]
```
:::
::::

### A signed plaintext footer

In the step that read one module, `open_bytes` decoded the plaintext footer with the reader's
footer decoder, the `metadata` module. That decoder refuses bytes left over after the
`FileMetaData`: they mean the trailer's length and the structure disagree. An encrypted file with
a plaintext footer leaves exactly a signature's worth, and says it uses encryption:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/metadata.py
:language: python
:start-at: # An encrypted file with a plaintext footer (ch13) signs it
:end-before: fmd = "FileMetaData"
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/metadata.rs
:language: rust
:start-at: // An encrypted file with a plaintext footer (ch13) signs it
:end-before: const FMD: &str = "FileMetaData";
```
:::
::::

### Refusing what it cannot read

The column reader refuses an encrypted column by name, rather than decoding ciphertext as if it
were a page, which is what a library without encryption does under *Ask a library* below:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/column.py
:language: python
:start-at: def refuse_encrypted(
:end-before: def decode_pages(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: fn refuse_encrypted(
:end-before: /// Decode pages already located
```
:::
::::

### Checking it

The fixtures were written by pyarrow with the keys, and the manifests describe them as pyarrow
saw them with the keys. The tests hold the keyless reader to that description: the encrypted
footer module is exactly the size pyarrow reports for the footer, the column chunks pyarrow found
fill exactly the bytes before it, the unencrypted columns decode to pyarrow's rows, and the
encrypted columns' modules tile their chunks.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests -k encrypt
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures encrypt
```
:::
::::

Encryption uses a fresh nonce for every module and a fresh data key for every file, so these two
fixtures cannot be regenerated byte for byte. They were written once; the generator's check
decrypts them with the published keys and confirms they still hold exactly the intended rows.

### Ask a library

At work a library reads these files, with keys from a key service. Without keys, pyarrow and the
`parquet` crate stop where the book's reader stops, though not in the same way:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/modular_encryption/encryption_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/encryption_with_a_library.rs
:language: rust
```
:::
::::

Both open the plaintext footer and count the rows. pyarrow gives the statistics of `order_id` and
`country` and reads those two columns. Asked for `email`, it refuses, because it cannot decrypt
the column's metadata. The crate, built here without its `encryption` feature, finds no
statistics for the two encrypted columns, as the book's reader found none. But it does not know
that `email`'s pages are encrypted: it reads the first module's length prefix as the start of a
page header, and fails on a field the header lacks. The book's reader refuses the column by name
before it reads a page. Neither library opens the encrypted footer without keys.

The Python step keeps away from one call. pyarrow's metadata for an encrypted column,
`metadata.row_group(0).column(2)`, needs that column's key. Without the key, pyarrow does not
raise an error: it stops the whole Python process, and in the page that stops every step. A
reader with keys passes decryption properties from `pyarrow.parquet.encryption`, as the pyarrow
documentation under *Where to go next* shows. Ask for the other encrypted column,
`amount_cents`, instead of `email`: both libraries fail on it as they did on `email`.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin encryption_with_a_library
```

## What this cannot tell you

**How to decrypt.** This reader stops where the keys would be needed. Decrypting needs AES, GCM,
the service that unwraps data keys, and the exact authenticated data for each module; the format
specifies all of them, and this book does not implement them.

**Whether to encrypt.** Encryption protects files wherever they are copied. Access control on the
storage protects them only where they are stored. Which risk matters is a question about the
data, not the format.

**How table formats use it.** Engines that manage many files, [ch14](#lakehouse-and-beyond)'s
subject, decide which columns to encrypt and hold the keys; the files only carry the result.

## Key takeaways

:::{div}
:class: takeaways

- **Parquet encrypts modules, not files.** The footer and every page header and page are
  encrypted separately, so pages can still be read one at a time.
- **A plaintext footer keeps the file readable without keys**, except for the encrypted columns,
  whose values and statistics are hidden.
- **An encrypted footer hides the whole layout.** Without the footer key even unencrypted columns
  cannot be found.
- **Files name keys; they never hold them.** Data keys are wrapped by master keys that stay in a
  key service.
- **Encryption hides values, not shape.** Sizes, page counts and page lengths remain visible.
:::

## Problems

Three, in `exercises/python/modular_encryption.py`, or in Rust in
`exercises/src/modular_encryption.rs`. The first two have tests. The third has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: modular_encryption
```

**13.1 Find the modules.** Split an encrypted column chunk into its modules by their length
prefixes. The test compares your modules with the reader's for both encrypted columns, and with
generated chunks.

**13.2 Which footer mode?** Tell an unencrypted file, a plaintext footer and an encrypted footer
apart. The test checks every fixture.

**13.3 Your own threat model.** No test: the data is yours. Pick a table with sensitive columns
and decide which to encrypt, and whether the footer should be. List what a reader without keys
would still learn in your choice, from the sizes, offsets and page counts this chapter showed.
A good answer names one thing the plaintext footer reveals that matters for your data, and says
whether that justifies an encrypted footer and the cost of making every reader hold a key.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_13_1` in Python, or `problem_13_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_modular_encryption.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test modular_encryption -- --ignored
```
:::
::::

## Where to go next

- Modular encryption is specified in the format repository's
  [Encryption.md](https://github.com/apache/parquet-format/blob/master/Encryption.md).
- pyarrow's
  [encryption documentation](https://arrow.apache.org/docs/python/parquet.html#parquet-modular-encryption-columnar-encryption)
  shows how a real key service is plugged in.
- AES-GCM is specified in NIST Special Publication 800-38D.
- [ch14](#lakehouse-and-beyond) turns from one file to the many that make a table.
