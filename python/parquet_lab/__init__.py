"""parquet_lab: a Parquet reader small enough to read in full, built in the order the book
teaches it.

The same reader exists in Rust, in ``crates/parquet-lab``. Both are tested against the files
pyarrow wrote and against each other: for every report the browser draws, the two must return
the same JSON. Each module here has a Rust module of the same name.

| Module | What it does | Chapter |
|---|---|---|
| ``layout`` | one table stored by rows and by columns | ch01 |
| ``bytes`` | little-endian integers, varints, zigzag, spans | ch02 |
| ``format`` | the magic bytes, the trailer, where the footer is | ch02 |
| ``thrift`` | Thrift's compact protocol, decoded without a schema | ch02 |
| ``parquet_thrift`` | the names ``parquet.thrift`` gives to field ids | ch03 |
| ``logical`` | logical types | ch03 |
| ``metadata`` | ``FileMetaData`` as Python types | ch03, ch08 |
| ``pages`` | walking a column chunk's page headers | ch06 |
| ``page_index``, ``bloom`` | where the page index and Bloom filters are | ch09 |
| ``crypto`` | encrypted modules, described without keys | ch13 |
| ``object_store`` | a simulated S3: ``HEAD``, ``GET``, ranges, and a trace | ch02, ch10 |
| ``reader`` | opening a file in an object store | ch02 |
| ``report`` | what the reader did, as JSON | all |
| ``browser`` | the calls the browser's Python engine makes | all |

It uses the standard library only, so it runs unchanged under CPython and, in the page, under
Pyodide.
"""
