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

```lab
experiment: encryption
fixture: plaintext-footer.parquet
fixtures: plaintext-footer.parquet, encrypted-footer.parquet
```

The panel lists what the reader could read and what it could not, and each item marks the bytes
it concerns. Try these:

1. **As loaded.** The schema, the row count, and the unencrypted columns' values and statistics
   are all readable. So are the names of the keys that protect the other two columns.
2. **Open `email` in the structure view.** Its pages are two encrypted modules: a page header and
   a page, each with a length, a nonce, ciphertext and a tag.
3. **Find the signature.** In the structure view, after the `FileMetaData`, a nonce and a tag
   sign the footer.
4. **Switch to `encrypted-footer.parquet`.** The file starts and ends with `PARE`. The reader can
   name the algorithm and the footer key, and nothing else.

### Modules

Parquet encrypts **modules**, not files. Every encrypted piece is laid out the same way:

```text
[length: u32, little-endian]   the bytes that follow
[nonce: 12 bytes]              never reused under one key
[ciphertext]                   the module, encrypted with AES
[tag: 16 bytes]                AES-GCM's check that nothing was changed
```

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

### Keys by name

Neither file holds a key. Each encrypted piece carries **key metadata**, which names a key
without revealing it. pyarrow writes it as JSON:

```text
{"keyMaterialType":"PKMT1", ..., "masterKeyID":"pii", "wrappedDEK":"…", ...}
```

The scheme is envelope encryption. Each column is encrypted with a random data key. That data key
is wrapped, encrypted, with a master key that stays inside a key management service. A reader
sends the wrapped data key to the service, which unwraps it only for a reader allowed to have
it. Different columns can use different master keys, so one reader may see `amount_cents` and
not `email`.

The fixtures use a toy key service that wraps by XOR with master keys published in
`fixtures/generate.py`. It protects nothing, on purpose: the files exist to show what encryption
hides from a reader without keys, and anyone may regenerate them.

### What still leaks

Encryption hides values, not shape. From the tables above and the structure view, a reader
without keys still learns:

- **the file's size, and in a plaintext footer every column chunk's size and offset;**
- **how many pages each encrypted column has, and how long each is.** AES-GCM does not change a
  module's length, so the ciphertext is exactly as long as the page, and page lengths can say
  something about the values;
- **which columns are protected, and by which named keys.**

The encrypted footer hides more of the shape, at the price of making the whole file unreadable
without the footer key.

## Building it

### Walking modules

A module is read from its length prefix alone, and an encrypted column chunk is a run of them:

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

### A signed plaintext footer

The footer decoder from [ch02](#anatomy-of-a-parquet-file) refused bytes left over after the
`FileMetaData`. An encrypted file with a plaintext footer leaves exactly a signature's worth, and
says it uses encryption:

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
were a page:

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

**13.1 Find the modules.** Split an encrypted column chunk into its modules by their length
prefixes. The test compares your modules with the reader's for both encrypted columns, and with
generated chunks.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_modular_encryption.py --problems -k problem_13_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test modular_encryption problem_13_1 -- --ignored
```
:::
::::

**13.2 Which footer mode?** Tell an unencrypted file, a plaintext footer and an encrypted footer
apart. The test checks every fixture.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_modular_encryption.py --problems -k problem_13_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test modular_encryption problem_13_2 -- --ignored
```
:::
::::

**13.3 Your own threat model.** No test: the data is yours. Pick a table with sensitive columns
and decide which to encrypt, and whether the footer should be. List what a reader without keys
would still learn in your choice, from the sizes, offsets and page counts this chapter showed.
A good answer names one thing the plaintext footer reveals that matters for your data, and says
whether that justifies an encrypted footer and the cost of making every reader hold a key.

## Where to go next

- Modular encryption is specified in the format repository's
  [Encryption.md](https://github.com/apache/parquet-format/blob/master/Encryption.md).
- pyarrow's
  [encryption documentation](https://arrow.apache.org/docs/python/parquet.html#parquet-modular-encryption-columnar-encryption)
  shows how a real key service is plugged in.
- AES-GCM is specified in NIST Special Publication 800-38D.
- [ch14](#lakehouse-and-beyond) turns from one file to the many that make a table.
