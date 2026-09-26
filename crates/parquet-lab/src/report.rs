//! What the implementation found, as JSON: the one format the browser, the command line and the
//! book's figures all read.
//!
//! Nothing here decides anything. Every function runs the reader and writes down what it did,
//! so the page that shows a footer length, a byte range or a request is showing a value this
//! crate computed. The browser gets the same JSON from the WASM build that `pqlab` prints on a
//! terminal, and `tests/wasm_matches_native.py` holds the two to being byte-identical.

use crate::bytes::{le_terms, Span};
use crate::encoding::{hex, plain_scalar};
use crate::format::{check_header, footer_span, parse_trailer, TRAILER_LEN};
use crate::json::{obj, Json};
use crate::metadata::{decode_file_metadata, ColumnChunk, FileMetaData};
use crate::object_store::{MemoryStore, NetworkModel, Request, TracingStore};
use crate::pages::walk_pages;
use crate::parquet_thrift::{enum_value_name, field_def, Kind};
use crate::reader::{read_footer, FooterOptions, FooterRead, SizeSource};
use crate::thrift::{Node, Value};

/// Open `file` through a simulated object store, and report every step and every request.
///
/// The file is put in a [`MemoryStore`] under `key`, and the reader sees it only through a
/// [`TracingStore`]. It gets no other access to the bytes. What it reports as fetched is
/// therefore exactly what it asked for.
pub fn footer_lab(file: &[u8], key: &str, options: FooterOptions, model: NetworkModel) -> Json {
    let mut store = MemoryStore::new();
    store.put(key, file.to_vec());
    let mut traced = TracingStore::new(store, model);
    let result = read_footer(&mut traced, key, options);

    let base = obj([
        ("key", key.into()),
        ("options", options_json(options, model)),
        ("requests", requests_json(&traced.requests)),
        (
            "totals",
            obj([
                ("requests", traced.requests.len().into()),
                ("bytes_returned", traced.bytes_returned().into()),
                ("elapsed_us", traced.elapsed_us().into()),
            ]),
        ),
        (
            "fetched",
            Json::Arr(
                traced
                    .requests
                    .iter()
                    .filter_map(|r| r.returned.map(Json::from))
                    .collect(),
            ),
        ),
    ]);
    match result {
        Err(e) => base.with("ok", false).with("error", e.to_string()),
        Ok(read) => {
            let useful = TRAILER_LEN + read.footer.len();
            base.with("ok", true)
                .with("file_size", read.file_size)
                .with("tail", read.tail)
                .with("trailer", trailer_json(&read))
                .with(
                    "footer",
                    obj([
                        ("span", read.footer.into()),
                        ("length", read.footer.len().into()),
                        ("prefetched", read.footer_was_prefetched.into()),
                    ]),
                )
                .with("useful_bytes", useful)
                .with(
                    "overfetch_bytes",
                    traced.bytes_returned().saturating_sub(useful),
                )
                .with("metadata", metadata_summary(&read.metadata))
        }
    }
}

fn options_json(o: FooterOptions, m: NetworkModel) -> Json {
    let (size, known) = match o.size {
        SizeSource::Head => ("head", Json::Null),
        SizeSource::Known(n) => ("known", n.into()),
        SizeSource::SuffixRange => ("suffix", Json::Null),
    };
    obj([
        ("size_source", size.into()),
        ("known_size", known),
        ("prefetch", o.prefetch.into()),
        ("latency_us", m.latency_us.into()),
        ("bandwidth_bytes_per_sec", m.bandwidth_bytes_per_sec.into()),
    ])
}

pub fn requests_json(requests: &[Request]) -> Json {
    Json::Arr(
        requests
            .iter()
            .map(|r| {
                obj([
                    ("seq", r.seq.into()),
                    ("method", r.method.name().into()),
                    ("key", r.key.clone().into()),
                    ("range", r.range.clone().into()),
                    ("why", r.why.clone().into()),
                    ("status", u64::from(r.status).into()),
                    ("returned", r.returned.into()),
                    ("bytes", r.bytes_returned.into()),
                    ("start_us", r.start_us.into()),
                    ("end_us", r.end_us.into()),
                    ("connection", r.connection.into()),
                    ("phase", r.phase.into()),
                ])
            })
            .collect(),
    )
}

fn trailer_json(read: &FooterRead) -> Json {
    let t = &read.trailer;
    obj([
        ("span", t.span.into()),
        ("bytes", t.bytes.to_vec().into()),
        ("length_span", t.length_span().into()),
        ("magic_span", t.magic_span().into()),
        (
            "magic",
            String::from_utf8_lossy(&t.magic).into_owned().into(),
        ),
        ("footer_length", t.footer_length.into()),
        (
            "terms",
            Json::Arr(
                t.length_terms()
                    .into_iter()
                    .map(|(b, w)| {
                        obj([
                            ("byte", b.into()),
                            ("weight", w.into()),
                            ("product", (u64::from(b) * w).into()),
                        ])
                    })
                    .collect(),
            ),
        ),
    ])
}

fn metadata_summary(m: &FileMetaData) -> Json {
    obj([
        ("version", m.version.into()),
        ("num_rows", m.num_rows.into()),
        ("created_by", m.created_by.clone().into()),
        ("num_row_groups", m.row_groups.len().into()),
        (
            "columns",
            Json::Arr(
                m.leaves()
                    .into_iter()
                    .map(|e| {
                        obj([
                            ("name", e.name.clone().into()),
                            ("physical_type", e.physical_type.map(|t| t.name()).into()),
                            ("repetition", e.repetition.clone().into()),
                            (
                                "logical_type",
                                e.logical_type.as_ref().map(|l| l.to_string()).into(),
                            ),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("key_value_metadata", m.key_value_metadata.len().into()),
    ])
}

/// The whole file, parsed into the regions the structure view draws.
///
/// Unlike [`footer_lab`] this reads the bytes directly rather than through a store: it is a map
/// of the file, not a record of how a reader got there. Every node has a `span`, so selecting
/// it can highlight its bytes, and a `label` and `value` for the tree.
pub fn structure(file: &[u8]) -> Json {
    match structure_inner(file) {
        Ok(tree) => obj([
            ("ok", true.into()),
            ("file_size", file.len().into()),
            ("tree", tree),
        ]),
        Err(e) => obj([
            ("ok", false.into()),
            ("file_size", file.len().into()),
            ("error", e.into()),
        ]),
    }
}

fn region(label: &str, kind: &str, span: Span, value: Json, children: Vec<Json>) -> Json {
    obj([
        ("label", label.into()),
        ("kind", kind.into()),
        ("span", span.into()),
        ("value", value),
        ("children", Json::Arr(children)),
    ])
}

/// A module's parts, as structure regions.
fn module_region(label: &str, m: &crate::crypto::Module) -> Json {
    region(
        label,
        "encrypted",
        m.span,
        format!("{} bytes, encrypted", m.span.len()).into(),
        vec![
            region(
                "Length",
                "module_length",
                m.length,
                format!("{} (u32, little-endian)", m.span.len() - 4).into(),
                vec![],
            ),
            region(
                "Nonce",
                "nonce",
                m.nonce,
                "12 bytes, used once".into(),
                vec![],
            ),
            region("Ciphertext", "ciphertext", m.ciphertext, Json::Null, vec![]),
            region(
                "Tag",
                "tag",
                m.tag,
                "16 bytes: AES-GCM's check".into(),
                vec![],
            ),
        ],
    )
}

/// An encrypted-footer file, as far as a reader without the footer key can see it (ch13).
fn encrypted_structure(file: &[u8]) -> Result<Json, String> {
    let size = file.len() as u64;
    let e = crate::crypto::encrypted_footer(file)?;
    let last = Span::new(size - TRAILER_LEN, size);
    Ok(region(
        "Parquet file",
        "file",
        Span::new(0, size),
        format!("{size} bytes").into(),
        vec![
            region("Header", "magic", Span::new(0, 4), "PARE".into(), vec![]),
            region(
                "Data",
                "encrypted",
                Span::new(4, e.footer.start),
                "row groups the reader cannot locate without the footer".into(),
                vec![],
            ),
            region(
                "Footer",
                "footer",
                e.footer,
                "FileCryptoMetaData, then the encrypted FileMetaData".into(),
                vec![
                    annotate(
                        &e.crypto_metadata,
                        "FileCryptoMetaData",
                        "FileCryptoMetaData",
                        None,
                    ),
                    module_region("Encrypted FileMetaData", &e.module),
                ],
            ),
            region(
                "Trailer",
                "trailer",
                last,
                Json::Null,
                vec![
                    region(
                        "Footer length",
                        "footer_length",
                        Span::new(last.start, last.start + 4),
                        format!("{} (u32, little-endian)", e.footer.len()).into(),
                        vec![],
                    ),
                    region(
                        "Magic",
                        "magic",
                        Span::new(last.start + 4, last.end),
                        "PARE".into(),
                        vec![],
                    ),
                ],
            ),
        ],
    ))
}

fn structure_inner(file: &[u8]) -> Result<Json, String> {
    let size = file.len() as u64;
    if size < crate::format::MIN_FILE_LEN {
        return Err(format!("{size} bytes is too short to be a Parquet file"));
    }
    if file[..4] == crate::crypto::MAGIC_ENCRYPTED {
        return encrypted_structure(file);
    }
    let header = check_header([file[0], file[1], file[2], file[3]]).map_err(|e| e.to_string())?;
    let last8: [u8; 8] = file[file.len() - 8..].try_into().unwrap();
    let trailer = parse_trailer(last8, size).map_err(|e| e.to_string())?;
    let footer = footer_span(size, trailer.footer_length).map_err(|e| e.to_string())?;
    let footer_bytes = &file[footer.start as usize..footer.end as usize];
    let md = decode_file_metadata(footer_bytes, footer.start).map_err(|e| e.to_string())?;

    let mut top = vec![region("Header", "magic", header, "PAR1".into(), vec![])];
    for (i, rg) in md.row_groups.iter().enumerate() {
        let chunks: Vec<Json> = rg
            .columns
            .iter()
            .map(|c| chunk_region(file, c))
            .collect::<Result<_, _>>()?;
        let ranges: Vec<Span> = rg.columns.iter().map(ColumnChunk::byte_range).collect();
        let span = match (
            ranges.iter().map(|s| s.start).min(),
            ranges.iter().map(|s| s.end).max(),
        ) {
            (Some(a), Some(b)) => Span::new(a, b),
            _ => Span::new(header.end, header.end),
        };
        top.push(region(
            &format!("Row group {i}"),
            "row_group",
            span,
            format!("{} rows", rg.num_rows).into(),
            chunks,
        ));
    }
    // Bloom filters and the page index (ch09), between the last row group and the footer.
    let mut extra: Vec<(Span, Json)> = Vec::new();
    for (g, rg) in md.row_groups.iter().enumerate() {
        for c in &rg.columns {
            let name = format!("{} (row group {g})", c.dotted_path());
            if let Ok(Some(b)) = crate::bloom::read(file, c) {
                let span = Span::new(b.header_span.start, b.bitset_span.end);
                let bitset = region(
                    "Bitset",
                    "bloom_bitset",
                    b.bitset_span,
                    format!("{} blocks of 32 bytes", b.num_blocks()).into(),
                    vec![],
                );
                let header = annotate(&b.header, "BloomFilterHeader", "BloomFilterHeader", None);
                extra.push((
                    span,
                    region(
                        &format!("Bloom filter {name}"),
                        "bloom",
                        span,
                        Json::Null,
                        vec![header, bitset],
                    ),
                ));
            }
            if let Ok(Some(ci)) = crate::page_index::column_index(file, c) {
                let tree = annotate(&ci.tree, "ColumnIndex", "ColumnIndex", Some(c));
                extra.push((
                    ci.span,
                    region(
                        &format!("Column index {name}"),
                        "column_index",
                        ci.span,
                        Json::Null,
                        vec![tree],
                    ),
                ));
            }
            if let Ok(Some(oi)) = crate::page_index::offset_index(file, c) {
                let tree = annotate(&oi.tree, "OffsetIndex", "OffsetIndex", None);
                extra.push((
                    oi.span,
                    region(
                        &format!("Offset index {name}"),
                        "offset_index",
                        oi.span,
                        Json::Null,
                        vec![tree],
                    ),
                ));
            }
        }
    }
    extra.sort_by_key(|(s, _)| *s);
    if let (Some(first), Some(last)) = (extra.first(), extra.last()) {
        let span = Span::new(first.0.start, last.0.end);
        let count = extra.len();
        top.push(region(
            "Indexes and filters",
            "indexes",
            span,
            format!("{count} structures").into(),
            extra.into_iter().map(|(_, j)| j).collect(),
        ));
    }
    let mut footer_children = vec![annotate(&md.tree, "FileMetaData", "FileMetaData", None)];
    if let Some(sig) = md.footer_signature {
        footer_children.push(region(
            "Signature",
            "signature",
            sig,
            "a nonce and an AES-GCM tag made with the footer key".into(),
            vec![
                region(
                    "Nonce",
                    "nonce",
                    Span::new(sig.start, sig.start + 12),
                    Json::Null,
                    vec![],
                ),
                region(
                    "Tag",
                    "tag",
                    Span::new(sig.start + 12, sig.end),
                    Json::Null,
                    vec![],
                ),
            ],
        ));
    }
    top.push(region(
        "Footer",
        "footer",
        footer,
        "FileMetaData".into(),
        footer_children,
    ));
    top.push(region(
        "Trailer",
        "trailer",
        trailer.span,
        Json::Null,
        vec![
            region(
                "Footer length",
                "footer_length",
                trailer.length_span(),
                format!("{} (u32, little-endian)", trailer.footer_length).into(),
                vec![],
            ),
            region(
                "Magic",
                "magic",
                trailer.magic_span(),
                "PAR1".into(),
                vec![],
            ),
        ],
    ));
    Ok(region(
        "Parquet file",
        "file",
        Span::new(0, size),
        format!("{size} bytes").into(),
        top,
    ))
}

fn chunk_region(file: &[u8], c: &ColumnChunk) -> Result<Json, String> {
    let range = c.byte_range();
    if range.end > file.len() as u64 {
        return Err(format!(
            "column chunk {} claims bytes {range}, past the end of the file",
            c.dotted_path()
        ));
    }
    if let Some(crypto) = &c.crypto {
        // Encrypted pages cannot be walked by their headers; their modules can, by length.
        let modules = crate::crypto::chunk_modules(file, range)
            .map_err(|e| format!("column chunk {}: {e}", c.dotted_path()))?;
        let children = modules
            .iter()
            .enumerate()
            .map(|(i, m)| {
                module_region(
                    if i % 2 == 0 {
                        "Encrypted page header"
                    } else {
                        "Encrypted page"
                    },
                    m,
                )
            })
            .collect();
        let key = if crypto.with_column_key {
            "its own key"
        } else {
            "the footer key"
        };
        return Ok(region(
            &format!("Column chunk {}", c.dotted_path()),
            "column_chunk",
            range,
            format!(
                "{} · encrypted with {key} · {} modules",
                c.physical_type.name(),
                modules.len()
            )
            .into(),
            children,
        ));
    }
    let pages = walk_pages(&file[range.start as usize..range.end as usize], range.start)
        .map_err(|e| format!("column chunk {}: {e}", c.dotted_path()))?;
    let children = pages
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let mut detail = format!(
                "{} bytes, {} values",
                p.compressed_page_size,
                p.num_values.unwrap_or(0)
            );
            if let Some(e) = &p.encoding {
                detail.push_str(&format!(", {e}"));
            }
            region(
                &format!("Page {i}: {}", p.page_type),
                "page",
                p.span(),
                detail.into(),
                vec![
                    region(
                        "Page header",
                        "page_header",
                        p.header_span,
                        "PageHeader".into(),
                        vec![annotate(&p.header, "PageHeader", "PageHeader", Some(c))],
                    ),
                    region(
                        "Page body",
                        "page_body",
                        p.body_span,
                        "values".into(),
                        vec![],
                    ),
                ],
            )
        })
        .collect();
    let mut value = format!(
        "{} · {} · {}",
        c.physical_type.name(),
        c.encodings.join(", "),
        c.codec
    );
    if let Some(s) = &c.statistics {
        if let (Some(lo), Some(hi)) = (&s.min_value, &s.max_value) {
            value.push_str(&format!(
                " · min {} max {}",
                plain_scalar(c.physical_type, lo).unwrap_or_else(|| hex(lo)),
                plain_scalar(c.physical_type, hi).unwrap_or_else(|| hex(hi)),
            ));
        }
    }
    Ok(region(
        &format!("Column chunk {}", c.dotted_path()),
        "column_chunk",
        range,
        value.into(),
        children,
    ))
}

/// A decoded Thrift node with Parquet's names attached, for the structure view.
///
/// `column` is the column chunk a page header belongs to, when there is one, so statistics can
/// be shown as values rather than bytes.
pub fn annotate(
    node: &Node,
    type_name: &'static str,
    label: &str,
    column: Option<&ColumnChunk>,
) -> Json {
    annotate_node(node, Kind::Struct(type_name), label, node.span, column)
}

fn annotate_node(
    node: &Node,
    kind: Kind,
    label: &str,
    span: Span,
    column: Option<&ColumnChunk>,
) -> Json {
    let (type_name, value, children) = match (&node.value, kind) {
        (Value::Struct(s), _) => {
            let struct_name = match kind {
                Kind::Struct(n) => n,
                _ => "",
            };
            let children = s
                .fields
                .iter()
                .map(|f| {
                    let def = field_def(struct_name, f.id);
                    let name = def
                        .map(|d| d.name.to_string())
                        .unwrap_or(format!("field {}", f.id));
                    let child_kind = def.map(|d| d.kind).unwrap_or(Kind::Int);
                    annotate_node(&f.node, child_kind, &name, f.span(), column)
                        .with("field_id", i64::from(f.id))
                        .with("header", f.header)
                })
                .collect();
            let shown = if struct_name.is_empty() {
                "struct".to_string()
            } else {
                struct_name.to_string()
            };
            (shown, Json::Null, children)
        }
        (Value::List(items), _) => {
            let inner = match kind {
                Kind::ListOf(k) => *k,
                _ => Kind::Int,
            };
            let children = items
                .iter()
                .enumerate()
                .map(|(i, item)| annotate_node(item, inner, &format!("[{i}]"), item.span, column))
                .collect();
            (
                format!("list<{}>", kind_name(inner)),
                format!(
                    "{} item{}",
                    items.len(),
                    if items.len() == 1 { "" } else { "s" }
                )
                .into(),
                children,
            )
        }
        (Value::Int(v), Kind::Enum(e)) => (
            "enum".to_string(),
            match enum_value_name(e, *v) {
                Some(name) => format!("{v} → {name}").into(),
                None => format!("{v}").into(),
            },
            vec![],
        ),
        (Value::Int(v), _) => ("int".to_string(), Json::Int(*v), vec![]),
        (Value::Bool(b), _) => ("bool".to_string(), Json::Bool(*b), vec![]),
        (Value::Double(d), _) => ("double".to_string(), Json::Float(*d), vec![]),
        (Value::Binary(b), Kind::Str) => (
            "string".to_string(),
            format!("{:?}", String::from_utf8_lossy(b)).into(),
            vec![],
        ),
        (Value::Binary(b), _) => {
            let shown = match (column, label) {
                (Some(c), "min_value" | "max_value" | "min" | "max") => {
                    plain_scalar(c.physical_type, b).map(|v| format!("{} → {v}", hex(b)))
                }
                _ => None,
            };
            (
                "binary".to_string(),
                shown.unwrap_or_else(|| hex(b)).into(),
                vec![],
            )
        }
        (Value::Map(entries), _) => (
            "map".to_string(),
            format!("{} entries", entries.len()).into(),
            vec![],
        ),
    };
    obj([
        ("label", label.into()),
        ("kind", "thrift".into()),
        ("type", type_name.into()),
        ("span", span.into()),
        ("value", value),
        ("children", Json::Arr(children)),
    ])
}

fn kind_name(k: Kind) -> String {
    match k {
        Kind::Int => "int".into(),
        Kind::Bool => "bool".into(),
        Kind::Str => "string".into(),
        Kind::Bytes => "binary".into(),
        Kind::Enum(e) => format!("{e:?}"),
        Kind::Struct(s) => s.into(),
        Kind::ListOf(inner) => format!("list<{}>", kind_name(*inner)),
    }
}

/// Every reasonable reading of the bytes starting at `offset`: the byte inspector.
///
/// A byte means nothing on its own. It is a value only once you decide how many bytes belong to
/// it and in which order, and this lists the choices side by side, all computed here.
pub fn interpret(file: &[u8], offset: u64) -> Json {
    let at = offset as usize;
    if at >= file.len() {
        return obj([
            ("ok", false.into()),
            ("error", format!("offset {offset} is past the end").into()),
        ]);
    }
    let rest = &file[at..];
    let take = |n: usize| -> Option<&[u8]> { rest.get(..n) };
    let mut out = obj([
        ("ok", true.into()),
        ("offset", offset.into()),
        ("byte", rest[0].into()),
        ("hex", format!("{:02x}", rest[0]).into()),
        ("binary", format!("{:08b}", rest[0]).into()),
        ("i8", i64::from(rest[0] as i8).into()),
        (
            "ascii",
            if rest[0].is_ascii_graphic() || rest[0] == b' ' {
                Json::Str((rest[0] as char).to_string())
            } else {
                Json::Null
            },
        ),
    ]);
    if let Some(b) = take(2) {
        out = out.with("u16_le", u64::from(u16::from_le_bytes([b[0], b[1]])));
    }
    if let Some(b) = take(4) {
        let arr = [b[0], b[1], b[2], b[3]];
        out = out
            .with("u32_le", u64::from(u32::from_le_bytes(arr)))
            .with("i32_le", i64::from(i32::from_le_bytes(arr)))
            .with("f32_le", f64::from(f32::from_le_bytes(arr)))
            .with("u32_le_terms", terms_json(b));
    }
    if let Some(b) = take(8) {
        let arr: [u8; 8] = b.try_into().unwrap();
        out = out
            .with("u64_le", u64::from_le_bytes(arr))
            .with("i64_le", i64::from_le_bytes(arr))
            .with("f64_le", f64::from_le_bytes(arr));
    }
    let mut r = crate::bytes::ByteReader::new(rest, offset);
    if let Ok(v) = r.read_uleb128() {
        let len = r.offset() - offset;
        out = out.with(
            "uleb128",
            obj([
                ("value", v.into()),
                ("length", len.into()),
                ("zigzag", crate::bytes::zigzag_decode(v).into()),
            ]),
        );
    }
    out.with(
        "thrift_field_header",
        obj([
            ("delta", u64::from(rest[0] >> 4).into()),
            ("type_nibble", u64::from(rest[0] & 0x0f).into()),
            (
                "type",
                crate::thrift::WireType::from_nibble(rest[0] & 0x0f)
                    .map(|w| w.name())
                    .into(),
            ),
        ]),
    )
}

fn terms_json(b: &[u8]) -> Json {
    Json::Arr(
        le_terms(b)
            .into_iter()
            .map(|(byte, w)| obj([("byte", byte.into()), ("weight", w.into())]))
            .collect(),
    )
}

/// Parse `file` fully and return its metadata, or why not. For the command line and the tests.
pub fn open_bytes(file: &[u8]) -> Result<FileMetaData, String> {
    let mut store = MemoryStore::new();
    store.put("file", file.to_vec());
    read_footer(&mut store, "file", FooterOptions::default())
        .map(|r| r.metadata)
        .map_err(|e| e.to_string())
}

/// Ch01's experiment: one query against the same table in both layouts, read through the
/// simulated object store.
///
/// `column_mask` has bit `c` set for each column the query projects. `row` is one row to fetch,
/// or `None` for every row. Each layout is stored as an object and read twice: once range by
/// range, asking only for the bytes the query needs, and once as a single whole-object `GET`.
/// Both reads are real requests against the store, and their traces are returned.
pub fn layouts(column_mask: u32, row: Option<usize>, model: NetworkModel) -> Json {
    use crate::layout::{encode, ranges, Layout, Query, Table};
    use crate::object_store::{GetRange, ObjectStore};

    let table = Table::sales();
    let columns: Vec<usize> = (0..table.columns.len())
        .filter(|c| column_mask & (1 << c) != 0)
        .collect();
    let rows: Vec<usize> = match row {
        Some(r) if r < table.rows.len() => vec![r],
        _ => (0..table.rows.len()).collect(),
    };
    let query = Query { columns, rows };

    let layout_json = |layout: Layout, key: &str| {
        let enc = encode(&table, layout);
        let needed = ranges(&enc, &query);
        let mut store = MemoryStore::new();
        store.put(key, enc.bytes.clone());

        let mut by_range = TracingStore::new(store.clone(), model);
        for (i, span) in needed.iter().enumerate() {
            let why = format!("range {} of {}: the query's values", i + 1, needed.len());
            by_range
                .get(key, GetRange::Bounded(*span), &why)
                .expect("a range computed from the encoding is inside it");
        }
        let mut whole = TracingStore::new(store, model);
        if !needed.is_empty() {
            whole
                .get(
                    key,
                    GetRange::Bounded(Span::new(0, enc.bytes.len() as u64)),
                    "the whole object, to pick the values out locally",
                )
                .expect("the whole object exists");
        }
        let needed_bytes: u64 = needed.iter().map(Span::len).sum();
        obj([
            (
                "layout",
                if layout == Layout::Rows {
                    "rows"
                } else {
                    "columns"
                }
                .into(),
            ),
            ("key", key.into()),
            ("bytes", enc.bytes.clone().into()),
            (
                "cells",
                Json::Arr(
                    enc.cells
                        .iter()
                        .map(|row| Json::Arr(row.iter().map(|s| Json::from(*s)).collect()))
                        .collect(),
                ),
            ),
            (
                "needed",
                Json::Arr(needed.iter().map(|s| Json::from(*s)).collect()),
            ),
            ("needed_bytes", needed_bytes.into()),
            ("total_bytes", enc.bytes.len().into()),
            (
                "by_range",
                obj([
                    ("requests", requests_json(&by_range.requests)),
                    ("bytes", by_range.bytes_returned().into()),
                    ("elapsed_us", by_range.elapsed_us().into()),
                ]),
            ),
            (
                "whole",
                obj([
                    ("requests", requests_json(&whole.requests)),
                    ("bytes", whole.bytes_returned().into()),
                    ("elapsed_us", whole.elapsed_us().into()),
                ]),
            ),
        ])
    };

    obj([
        ("ok", true.into()),
        (
            "columns",
            Json::Arr(table.columns.iter().map(|(n, _)| Json::from(*n)).collect()),
        ),
        (
            "rows",
            Json::Arr(
                table
                    .rows
                    .iter()
                    .map(|r| Json::Arr(r.iter().map(|c| Json::from(c.show())).collect()))
                    .collect(),
            ),
        ),
        (
            "query",
            obj([
                ("columns", query.columns.clone().into()),
                ("rows", query.rows.clone().into()),
            ]),
        ),
        (
            "model",
            obj([
                ("latency_us", model.latency_us.into()),
                (
                    "bandwidth_bytes_per_sec",
                    model.bandwidth_bytes_per_sec.into(),
                ),
            ]),
        ),
        ("rows_layout", layout_json(Layout::Rows, "sales.rows")),
        (
            "columns_layout",
            layout_json(Layout::Columns, "sales.columns"),
        ),
    ])
}

/// Ch03's experiment: the schema as the footer stores it, as the reader rebuilds it, and what
/// each column's statistics mean once its logical type is applied.
pub fn schema(file: &[u8]) -> Json {
    use crate::logical;
    use crate::schema::{build, leaves, to_text};

    let md = match open_bytes(file) {
        Ok(md) => md,
        Err(e) => return obj([("ok", false.into()), ("error", e.into())]),
    };
    let root = match build(&md.schema) {
        Ok(root) => root,
        Err(e) => return obj([("ok", false.into()), ("error", e.to_string().into())]),
    };
    let elements = Json::Arr(
        md.schema
            .iter()
            .enumerate()
            .map(|(i, e)| {
                obj([
                    ("index", i.into()),
                    ("name", e.name.clone().into()),
                    ("span", e.span.into()),
                    ("num_children", e.num_children.into()),
                    ("repetition", e.repetition.clone().into()),
                    ("physical_type", e.physical_type.map(|t| t.name()).into()),
                    ("type_length", e.type_length.into()),
                    (
                        "logical_type",
                        e.logical_type.as_ref().map(|l| l.to_string()).into(),
                    ),
                    ("converted_type", e.converted_type.clone().into()),
                ])
            })
            .collect(),
    );
    let reading = |c: &ColumnChunk,
                   lt: &Option<logical::LogicalType>,
                   bytes: &Option<Vec<u8>>,
                   span: Option<Span>| {
        match (bytes, span) {
            (Some(b), Some(s)) => obj([
                ("span", s.into()),
                ("hex", hex(b).into()),
                ("physical", plain_scalar(c.physical_type, b).into()),
                (
                    "logical",
                    lt.as_ref()
                        .and_then(|l| logical::interpret(c.physical_type, l, b))
                        .into(),
                ),
            ]),
            _ => Json::Null,
        }
    };
    let first_group = md.row_groups.first();
    let leaves_json = Json::Arr(
        leaves(&root)
            .iter()
            .map(|leaf| {
                let chunk = first_group.and_then(|rg| rg.columns.get(leaf.column));
                let stats = chunk.and_then(|c| {
                    c.statistics.as_ref().map(|s| {
                        obj([
                            ("span", s.span.into()),
                            (
                                "min",
                                reading(c, &leaf.logical_type, &s.min_value, s.min_span),
                            ),
                            (
                                "max",
                                reading(c, &leaf.logical_type, &s.max_value, s.max_span),
                            ),
                            ("null_count", s.null_count.into()),
                        ])
                    })
                });
                obj([
                    ("column", leaf.column.into()),
                    ("path", leaf.dotted_path().into()),
                    ("element", leaf.element.into()),
                    (
                        "repetitions",
                        Json::Arr(
                            leaf.repetitions
                                .iter()
                                .map(|r| Json::from(r.word()))
                                .collect(),
                        ),
                    ),
                    ("max_definition_level", leaf.max_definition_level.into()),
                    ("max_repetition_level", leaf.max_repetition_level.into()),
                    ("physical_type", leaf.physical_type.name().into()),
                    (
                        "logical_type",
                        leaf.logical_type.as_ref().map(|l| l.to_string()).into(),
                    ),
                    ("chunk", chunk.map(|c| Json::from(c.byte_range())).into()),
                    ("statistics", stats.unwrap_or(Json::Null)),
                ])
            })
            .collect(),
    );
    fn tree(node: &crate::schema::SchemaNode) -> Json {
        obj([
            ("name", node.name.clone().into()),
            ("element", node.element.into()),
            ("span", node.span.into()),
            ("repetition", node.repetition.word().into()),
            (
                "children",
                Json::Arr(node.children.iter().map(tree).collect()),
            ),
        ])
    }
    obj([
        ("ok", true.into()),
        ("elements", elements),
        ("tree", tree(&root)),
        ("text", to_text(&root).into()),
        ("leaves", leaves_json),
    ])
}

fn runs_json(stream: &Option<(Span, Vec<crate::rle::Run>)>) -> Json {
    match stream {
        None => Json::Null,
        Some((span, runs)) => obj([
            ("span", (*span).into()),
            (
                "runs",
                Json::Arr(
                    runs.iter()
                        .map(|r| {
                            obj([
                                ("kind", r.kind.name().into()),
                                ("header", r.header.into()),
                                ("body", r.body.into()),
                                ("values", r.values.clone().into()),
                            ])
                        })
                        .collect(),
                ),
            ),
        ]),
    }
}

/// Ch04's experiment: one column's levels and values, what each triple means, and the records
/// rebuilt from them.
pub fn levels(file: &[u8], column: usize) -> Json {
    use crate::column::read_column;
    use crate::logical::value_json;
    use crate::nested::{assemble, explain, path_fields};
    use crate::schema::{build, leaves};

    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let md = match open_bytes(file) {
        Ok(md) => md,
        Err(e) => return fail(e),
    };
    let root = match build(&md.schema) {
        Ok(r) => r,
        Err(e) => return fail(e.to_string()),
    };
    let all = leaves(&root);
    let columns = Json::Arr(
        all.iter()
            .map(|l| {
                let fields = path_fields(&root, l);
                obj([
                    ("column", l.column.into()),
                    ("path", l.dotted_path().into()),
                    (
                        "label",
                        fields
                            .last()
                            .map(|f| f.label.clone())
                            .unwrap_or_default()
                            .into(),
                    ),
                    ("max_definition_level", l.max_definition_level.into()),
                    ("max_repetition_level", l.max_repetition_level.into()),
                ])
            })
            .collect(),
    );
    let Some(leaf) = all.get(column) else {
        return fail(format!("the file has no column {column}"));
    };
    let fields = path_fields(&root, leaf);
    let mut pages = Vec::new();
    let mut triples = Vec::new();
    for (g, rg) in md.row_groups.iter().enumerate() {
        let data = match read_column(file, &rg.columns[leaf.column], leaf) {
            Ok(d) => d,
            Err(e) => return fail(e.to_string()).with("columns", columns),
        };
        for p in &data.pages {
            pages.push(obj([
                ("row_group", g.into()),
                ("span", p.page.span().into()),
                ("header", p.page.header_span.into()),
                ("repetition_levels", runs_json(&p.rep_levels)),
                ("definition_levels", runs_json(&p.def_levels)),
                ("values", p.values.into()),
            ]));
        }
        triples.extend(data.triples);
    }
    let records = assemble(&fields, leaf, &triples);
    obj([
        ("ok", true.into()),
        ("columns", columns),
        ("column", column.into()),
        ("path", leaf.dotted_path().into()),
        (
            "fields",
            Json::Arr(
                fields
                    .iter()
                    .map(|f| {
                        obj([
                            ("name", f.name.clone().into()),
                            ("label", f.label.clone().into()),
                            ("repetition", f.repetition.word().into()),
                            ("definition_level", f.def.into()),
                            ("repetition_level", f.rep.into()),
                            ("list", f.is_list.into()),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("max_definition_level", leaf.max_definition_level.into()),
        ("max_repetition_level", leaf.max_repetition_level.into()),
        ("pages", Json::Arr(pages)),
        (
            "triples",
            Json::Arr(
                triples
                    .iter()
                    .map(|t| {
                        obj([
                            ("rep", t.rep.into()),
                            ("def", t.def.into()),
                            (
                                "value",
                                t.value
                                    .as_ref()
                                    .map(|v| {
                                        value_json(
                                            leaf.physical_type,
                                            leaf.logical_type.as_ref(),
                                            v,
                                        )
                                    })
                                    .unwrap_or(Json::Null),
                            ),
                            ("value_span", t.value_span.into()),
                            ("explain", explain(&fields, t).into()),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("records", Json::Arr(records)),
    ])
}

/// What `values` would take as PLAIN: the size an encoding is saving against.
fn plain_size(
    physical: crate::metadata::PhysicalType,
    type_length: Option<i64>,
    values: &[&crate::plain::PlainValue],
) -> u64 {
    use crate::plain::PlainValue;
    match physical.0 {
        0 => (values.len() as u64).div_ceil(8),
        1 | 4 => 4 * values.len() as u64,
        2 | 5 => 8 * values.len() as u64,
        3 => 12 * values.len() as u64,
        7 => type_length.unwrap_or(0).max(0) as u64 * values.len() as u64,
        _ => values
            .iter()
            .map(|v| match v {
                PlainValue::Bytes(b) => 4 + b.len() as u64,
                _ => 0,
            })
            .sum(),
    }
}

/// Ch05's experiment: how one column's values are encoded, step by step, and what the encoding
/// saves against PLAIN.
pub fn encodings(file: &[u8], column: usize) -> Json {
    use crate::column::read_column;
    use crate::logical::value_json;
    use crate::schema::{build, leaves};

    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let md = match open_bytes(file) {
        Ok(md) => md,
        Err(e) => return fail(e),
    };
    let root = match build(&md.schema) {
        Ok(r) => r,
        Err(e) => return fail(e.to_string()),
    };
    let all = leaves(&root);
    let Some(leaf) = all.get(column) else {
        return fail(format!("the file has no column {column}"));
    };
    let columns = Json::Arr(
        all.iter()
            .enumerate()
            .map(|(i, l)| {
                let chunk = md.row_groups.first().and_then(|rg| rg.columns.get(i));
                obj([
                    ("column", l.column.into()),
                    ("path", l.dotted_path().into()),
                    (
                        "encodings",
                        chunk
                            .map(|c| Json::from(c.encodings.clone()))
                            .unwrap_or(Json::Null),
                    ),
                ])
            })
            .collect(),
    );
    let step_json = |s: &crate::decode::Step| {
        obj([
            ("label", s.label.clone().into()),
            ("span", s.span.into()),
            ("detail", s.detail.clone().into()),
        ])
    };
    let show = |v: &crate::plain::PlainValue| {
        value_json(leaf.physical_type, leaf.logical_type.as_ref(), v)
    };
    let mut pages = Vec::new();
    let mut values = Vec::new();
    let mut dictionary = Json::Null;
    let (mut encoded, mut plain_values) = (0u64, Vec::new());
    let mut data_all = Vec::new();
    for rg in &md.row_groups {
        match read_column(file, &rg.columns[leaf.column], leaf) {
            Ok(d) => data_all.push(d),
            Err(e) => return fail(e.to_string()).with("columns", columns),
        }
    }
    for data in &data_all {
        if let Some(d) = &data.dictionary {
            encoded += d.page.body_span.len();
            dictionary = obj([
                ("page", d.page.span().into()),
                ("header", d.page.header_span.into()),
                ("body", d.page.body_span.into()),
                (
                    "entries",
                    Json::Arr(
                        d.entries
                            .iter()
                            .enumerate()
                            .map(|(i, (v, s))| {
                                obj([
                                    ("index", i.into()),
                                    ("value", show(v)),
                                    ("span", (*s).into()),
                                ])
                            })
                            .collect(),
                    ),
                ),
            ]);
        }
        for p in &data.pages {
            encoded += p.values.len();
            pages.push(obj([
                ("span", p.page.span().into()),
                ("encoding", p.encoding.clone().into()),
                ("values", p.values.into()),
                ("steps", Json::Arr(p.steps.iter().map(step_json).collect())),
            ]));
        }
        for t in &data.triples {
            if let Some(v) = &t.value {
                plain_values.push(v);
                values.push(obj([
                    ("value", show(v)),
                    ("span", t.value_span.into()),
                    (
                        "extra",
                        Json::Arr(t.extra_spans.iter().map(|s| Json::from(*s)).collect()),
                    ),
                ]));
            }
        }
    }
    obj([
        ("ok", true.into()),
        ("columns", columns),
        ("column", column.into()),
        ("path", leaf.dotted_path().into()),
        ("physical_type", leaf.physical_type.name().into()),
        (
            "logical_type",
            leaf.logical_type.as_ref().map(|l| l.to_string()).into(),
        ),
        ("dictionary", dictionary),
        ("pages", Json::Arr(pages)),
        ("values", Json::Arr(values)),
        (
            "sizes",
            obj([
                ("encoded", encoded.into()),
                (
                    "plain",
                    plain_size(leaf.physical_type, leaf.type_length, &plain_values).into(),
                ),
                ("count", plain_values.len().into()),
            ]),
        ),
    ])
}

/// Ch06's experiment: every page of one column chunk, what its header says, where its parts are,
/// and which rows it holds.
pub fn pages(file: &[u8], column: usize) -> Json {
    use crate::column::read_column;
    use crate::logical;
    use crate::schema::{build, leaves};

    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let md = match open_bytes(file) {
        Ok(md) => md,
        Err(e) => return fail(e),
    };
    let root = match build(&md.schema) {
        Ok(r) => r,
        Err(e) => return fail(e.to_string()),
    };
    let all = leaves(&root);
    let Some(leaf) = all.get(column) else {
        return fail(format!("the file has no column {column}"));
    };
    let columns = Json::Arr(
        all.iter()
            .map(|l| {
                obj([
                    ("column", l.column.into()),
                    ("path", l.dotted_path().into()),
                ])
            })
            .collect(),
    );
    let stat = |c: &ColumnChunk, b: &Option<Vec<u8>>| -> Json {
        b.as_ref()
            .map(|b| {
                leaf.logical_type
                    .as_ref()
                    .and_then(|l| logical::interpret(c.physical_type, l, b))
                    .or_else(|| plain_scalar(c.physical_type, b))
                    .unwrap_or_else(|| hex(b))
            })
            .into()
    };
    let mut out = Vec::new();
    let mut row = 0u64;
    for (g, rg) in md.row_groups.iter().enumerate() {
        let chunk = &rg.columns[leaf.column];
        let range = chunk.byte_range();
        let Some(bytes) = file.get(range.start as usize..range.end as usize) else {
            return fail(format!("column chunk {range} is past the end of the file"));
        };
        let walked = match walk_pages(bytes, range.start) {
            Ok(p) => p,
            Err(e) => return fail(e.to_string()),
        };
        // Rows per page come from the decoded levels: a row starts wherever r is 0.
        let decoded = read_column(file, chunk, leaf).ok();
        let per_page: Vec<Vec<u32>> = (0..walked.len())
            .map(|i| {
                decoded
                    .as_ref()
                    .map(|d| {
                        d.triples
                            .iter()
                            .filter(|t| t.page == i)
                            .map(|t| t.rep)
                            .collect()
                    })
                    .unwrap_or_default()
            })
            .collect();
        let firsts = crate::column::first_rows(&per_page);
        let group_start = row;
        for (i, p) in walked.iter().enumerate() {
            let starts = decoded
                .as_ref()
                .map(|_| per_page[i].iter().filter(|&&r| r == 0).count() as u64);
            let data_page = decoded.as_ref().and_then(|d| {
                d.pages
                    .iter()
                    .find(|dp| dp.page.header_span == p.header_span)
            });
            let first_row = group_start + firsts[i];
            row += starts.unwrap_or(0);
            out.push(obj([
                ("row_group", g.into()),
                ("index", i.into()),
                ("type", p.page_type.clone().into()),
                ("span", p.span().into()),
                ("header", p.header_span.into()),
                ("body", p.body_span.into()),
                ("compressed_page_size", p.compressed_page_size.into()),
                ("uncompressed_page_size", p.uncompressed_page_size.into()),
                ("num_values", p.num_values.into()),
                ("encoding", p.encoding.clone().into()),
                (
                    "statistics",
                    p.statistics
                        .as_ref()
                        .map(|s| {
                            obj([
                                ("min", stat(chunk, &s.min_value)),
                                ("max", stat(chunk, &s.max_value)),
                                ("null_count", s.null_count.into()),
                            ])
                        })
                        .unwrap_or(Json::Null),
                ),
                ("crc", p.crc.into()),
                ("crc_ok", p.crc_ok.into()),
                (
                    "v2",
                    p.v2.map(|v| {
                        obj([
                            ("num_nulls", v.num_nulls.into()),
                            ("num_rows", v.num_rows.into()),
                            (
                                "definition_levels_byte_length",
                                v.definition_levels_byte_length.into(),
                            ),
                            (
                                "repetition_levels_byte_length",
                                v.repetition_levels_byte_length.into(),
                            ),
                            ("is_compressed", v.is_compressed.into()),
                        ])
                    })
                    .unwrap_or(Json::Null),
                ),
                (
                    "repetition_levels",
                    data_page
                        .and_then(|d| d.rep_levels.as_ref().map(|(s, _)| Json::from(*s)))
                        .unwrap_or(Json::Null),
                ),
                (
                    "definition_levels",
                    data_page
                        .and_then(|d| d.def_levels.as_ref().map(|(s, _)| Json::from(*s)))
                        .unwrap_or(Json::Null),
                ),
                (
                    "values",
                    data_page
                        .map(|d| Json::from(d.values))
                        .unwrap_or(Json::Null),
                ),
                (
                    "first_row",
                    if starts.is_some() && p.page_type != "DICTIONARY_PAGE" {
                        first_row.into()
                    } else {
                        Json::Null
                    },
                ),
                (
                    "rows_started",
                    starts.filter(|_| p.page_type != "DICTIONARY_PAGE").into(),
                ),
            ]));
        }
    }
    obj([
        ("ok", true.into()),
        ("columns", columns),
        ("column", column.into()),
        ("path", leaf.dotted_path().into()),
        ("pages", Json::Arr(out)),
    ])
}

/// Ch07's experiment: what compression did to every column chunk, and how one page of one
/// column was decompressed, token by token.
///
/// The sizes come from the footer, so they are reported for every codec. The tokens need a
/// decoder, so a page compressed with a codec [`crate::compress`] does not decode reports why
/// instead of tokens.
pub fn compression(file: &[u8], column: usize, page: Option<usize>) -> Json {
    use crate::compress::{decompress, supported, TokenKind};
    use crate::schema::{build, leaves};

    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let md = match open_bytes(file) {
        Ok(md) => md,
        Err(e) => return fail(e),
    };
    let root = match build(&md.schema) {
        Ok(r) => r,
        Err(e) => return fail(e.to_string()),
    };
    let all = leaves(&root);
    let Some(leaf) = all.get(column) else {
        return fail(format!("the file has no column {column}"));
    };
    // Every column chunk's two sizes, summed over the row groups.
    let chunks = Json::Arr(
        all.iter()
            .map(|l| {
                let cs: Vec<&ColumnChunk> = md
                    .row_groups
                    .iter()
                    .map(|rg| &rg.columns[l.column])
                    .collect();
                obj([
                    ("column", l.column.into()),
                    ("path", l.dotted_path().into()),
                    ("codec", cs.first().map(|c| c.codec.clone()).into()),
                    (
                        "uncompressed",
                        cs.iter()
                            .map(|c| c.total_uncompressed_size)
                            .sum::<i64>()
                            .into(),
                    ),
                    (
                        "compressed",
                        cs.iter()
                            .map(|c| c.total_compressed_size)
                            .sum::<i64>()
                            .into(),
                    ),
                ])
            })
            .collect(),
    );
    let Some(chunk) = md.row_groups.first().map(|rg| &rg.columns[leaf.column]) else {
        return fail("the file has no row groups".into());
    };
    let range = chunk.byte_range();
    let Some(bytes) = file.get(range.start as usize..range.end as usize) else {
        return fail(format!("column chunk {range} is past the end of the file"));
    };
    let walked = match walk_pages(bytes, range.start) {
        Ok(p) => p,
        Err(e) => return fail(e.to_string()),
    };
    // What the codec was given: the whole body, or in a version 2 data page only the values,
    // and only when the header says they are compressed.
    let sections: Vec<(Span, i64, bool)> = walked
        .iter()
        .map(|p| match p.v2 {
            Some(v2) => {
                let levels = (v2.repetition_levels_byte_length + v2.definition_levels_byte_length)
                    .clamp(0, p.body_span.len() as i64);
                let from = p.body_span.start + levels as u64;
                (
                    Span::new(from, p.body_span.end),
                    p.uncompressed_page_size - levels,
                    v2.is_compressed,
                )
            }
            None => (p.body_span, p.uncompressed_page_size, true),
        })
        .collect();
    let chosen = page.unwrap_or_else(|| {
        walked
            .iter()
            .position(|p| p.page_type != "DICTIONARY_PAGE")
            .unwrap_or(0)
    });
    let pages = Json::Arr(
        walked
            .iter()
            .zip(&sections)
            .enumerate()
            .map(|(i, (p, (section, size, compressed)))| {
                obj([
                    ("index", i.into()),
                    ("type", p.page_type.clone().into()),
                    ("span", p.span().into()),
                    ("header", p.header_span.into()),
                    ("compressed_section", (*section).into()),
                    ("section_compressed", (*compressed).into()),
                    ("compressed_page_size", p.compressed_page_size.into()),
                    ("uncompressed_page_size", p.uncompressed_page_size.into()),
                    ("section_uncompressed_size", (*size).into()),
                    ("encoding", p.encoding.clone().into()),
                ])
            })
            .collect(),
    );
    let decoded = match (walked.get(chosen), sections.get(chosen)) {
        (Some(_), Some((section, size, compressed))) => {
            let codec = if *compressed {
                chunk.codec.as_str()
            } else {
                "UNCOMPRESSED"
            };
            let input = &file[section.start as usize..section.end as usize];
            match decompress(codec, input, section.start, (*size).max(0) as usize) {
                Ok(d) => obj([
                    ("ok", true.into()),
                    ("codec", codec.into()),
                    ("bytes", hex(&d.bytes).into()),
                    (
                        "tokens",
                        Json::Arr(
                            d.tokens
                                .iter()
                                .map(|t| {
                                    let (kind, distance) = match t.kind {
                                        TokenKind::Header => ("header", Json::Null),
                                        TokenKind::Literal => ("literal", Json::Null),
                                        TokenKind::Copy { distance } => ("copy", distance.into()),
                                    };
                                    obj([
                                        ("kind", kind.into()),
                                        ("label", t.label.clone().into()),
                                        ("input", t.input.into()),
                                        ("output", t.output.into()),
                                        ("distance", distance),
                                        ("detail", t.detail.clone().into()),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                ]),
                Err(e) => obj([
                    ("ok", false.into()),
                    ("codec", codec.into()),
                    ("error", e.into()),
                ]),
            }
        }
        _ => obj([
            ("ok", false.into()),
            (
                "error",
                format!("the column chunk has no page {chosen}").into(),
            ),
        ]),
    };
    obj([
        ("ok", true.into()),
        ("file_size", file.len().into()),
        ("chunks", chunks),
        ("column", column.into()),
        ("path", leaf.dotted_path().into()),
        ("codec", chunk.codec.clone().into()),
        ("supported", supported(&chunk.codec).into()),
        ("pages", pages),
        ("page", chosen.into()),
        ("decompressed", decoded),
    ])
}

/// A statistics value for display: through the column's logical type when it has one, then as
/// its physical type, then as hex.
fn stat_display(leaf: &crate::schema::Leaf, bytes: &[u8]) -> String {
    leaf.logical_type
        .as_ref()
        .and_then(|l| crate::logical::interpret(leaf.physical_type, l, bytes))
        .or_else(|| plain_scalar(leaf.physical_type, bytes))
        .unwrap_or_else(|| hex(bytes))
}

/// A chunk whose every value is null has no minimum or maximum, and that is not a gap in the
/// statistics: the null count says everything a reader needs.
fn all_null(reason: String, null_count: Option<i64>, num_values: i64) -> String {
    match null_count {
        Some(n) if n == num_values && n > 0 => {
            "every value is null, so there is no minimum or maximum; the null count alone rules \
             the chunk out for any comparison with a value"
                .into()
        }
        _ => reason,
    }
}

/// Ch08's experiment: every column chunk's statistics, whether the reader may use them and
/// why, and for one chunk every field, the values in the column's order, and what a mistaken
/// order would have made of them.
pub fn statistics(file: &[u8], row_group: usize, column: usize) -> Json {
    use crate::column::read_column;
    use crate::schema::{build, leaves};
    use crate::stats::{bounds, Comparator, Source};

    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let md = match open_bytes(file) {
        Ok(md) => md,
        Err(e) => return fail(e),
    };
    let root = match build(&md.schema) {
        Ok(r) => r,
        Err(e) => return fail(e.to_string()),
    };
    let all = leaves(&root);
    let comparator_of = |l: &crate::schema::Leaf| {
        Comparator::for_leaf(l, md.schema[l.element].converted_type.as_deref())
    };
    let type_order = |l: &crate::schema::Leaf| {
        md.column_orders
            .as_ref()
            .and_then(|o| o.get(l.column))
            .is_some_and(|o| o == "TYPE_ORDER")
    };
    let source_name = |s: Source| match s {
        Source::MinMaxValue => "min_value and max_value",
        Source::Deprecated => "min and max (deprecated)",
    };
    let columns = Json::Arr(
        all.iter()
            .map(|l| {
                let cmp = comparator_of(l);
                let chunks = md
                    .row_groups
                    .iter()
                    .enumerate()
                    .map(|(g, rg)| {
                        let c = &rg.columns[l.column];
                        let verdict = match &c.statistics {
                            Some(s) => bounds(s, cmp, type_order(l)),
                            None => Err("the column chunk has no statistics".into()),
                        };
                        let null_count = c.statistics.as_ref().and_then(|s| s.null_count);
                        let verdict = verdict.map_err(|e| all_null(e, null_count, c.num_values));
                        match verdict {
                            Ok(b) => obj([
                                ("row_group", g.into()),
                                ("usable", true.into()),
                                ("min", stat_display(l, &b.min).into()),
                                ("max", stat_display(l, &b.max).into()),
                                ("source", source_name(b.source).into()),
                                ("null_count", null_count.into()),
                                ("num_rows", rg.num_rows.into()),
                            ]),
                            Err(reason) => obj([
                                ("row_group", g.into()),
                                ("usable", false.into()),
                                ("reason", reason.into()),
                                ("null_count", null_count.into()),
                                ("num_rows", rg.num_rows.into()),
                            ]),
                        }
                    })
                    .collect();
                obj([
                    ("column", l.column.into()),
                    ("path", l.dotted_path().into()),
                    (
                        "type",
                        crate::schema::physical_word(l.physical_type, l.type_length).into(),
                    ),
                    (
                        "logical",
                        md.schema[l.element]
                            .logical_type
                            .as_ref()
                            .map(|t| t.to_string())
                            .into(),
                    ),
                    ("order", cmp.order().name().into()),
                    ("comparator", cmp.name().into()),
                    ("chunks", Json::Arr(chunks)),
                ])
            })
            .collect(),
    );
    let row_groups = Json::Arr(
        md.row_groups
            .iter()
            .enumerate()
            .map(|(g, rg)| {
                obj([
                    ("index", g.into()),
                    ("num_rows", rg.num_rows.into()),
                    ("total_byte_size", rg.total_byte_size.into()),
                    (
                        "sorting_columns",
                        Json::Arr(
                            rg.sorting_columns
                                .iter()
                                .map(|s| {
                                    obj([
                                        ("column", s.column.into()),
                                        (
                                            "path",
                                            all.get(s.column.max(0) as usize)
                                                .map(|l| l.dotted_path())
                                                .into(),
                                        ),
                                        ("descending", s.descending.into()),
                                        ("nulls_first", s.nulls_first.into()),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                ])
            })
            .collect(),
    );
    let (Some(leaf), Some(rg)) = (all.get(column), md.row_groups.get(row_group)) else {
        return fail(format!("no column {column} in row group {row_group}"));
    };
    let chunk = &rg.columns[leaf.column];
    let cmp = comparator_of(leaf);
    // Every field of the Statistics struct the footer has, with the bytes that hold its value.
    let mut fields = Vec::new();
    if let Some(s) = &chunk.statistics {
        let mut value = |name: &str, bytes: &Option<Vec<u8>>, span: Option<Span>| {
            if let (Some(b), Some(sp)) = (bytes, span) {
                fields.push(obj([
                    ("name", name.into()),
                    ("span", sp.into()),
                    ("hex", hex(b).into()),
                    ("value", stat_display(leaf, b).into()),
                ]));
            }
        };
        value("min_value", &s.min_value, s.min_span);
        value("max_value", &s.max_value, s.max_span);
        value("min", &s.min, s.min_deprecated_span);
        value("max", &s.max, s.max_deprecated_span);
        for (name, v) in [
            ("null_count", s.null_count.map(|n| n.to_string())),
            ("distinct_count", s.distinct_count.map(|n| n.to_string())),
            (
                "is_min_value_exact",
                s.is_min_value_exact.map(|b| b.to_string()),
            ),
            (
                "is_max_value_exact",
                s.is_max_value_exact.map(|b| b.to_string()),
            ),
        ] {
            if let Some(v) = v {
                fields.push(obj([
                    ("name", name.into()),
                    ("span", s.span.into()),
                    ("hex", Json::Null),
                    ("value", v.into()),
                ]));
            }
        }
    }
    let verdict = match &chunk.statistics {
        Some(s) => bounds(s, cmp, type_order(leaf))
            .map_err(|e| all_null(e, s.null_count, chunk.num_values)),
        None => Err("the column chunk has no statistics".into()),
    };
    // The values themselves, decoded, and what each order makes of them.
    let (values, nulls) = match read_column(file, chunk, leaf) {
        Ok(d) => (
            Some(
                d.triples
                    .iter()
                    .filter_map(|t| t.value.as_ref())
                    .map(|v| v.to_plain_bytes(leaf.physical_type))
                    .collect::<Vec<_>>(),
            ),
            d.triples.iter().filter(|t| t.value.is_none()).count(),
        ),
        Err(_) => (None, 0),
    };
    let values_json = match &values {
        Some(vs) => {
            let mut placed: Vec<&Vec<u8>> =
                vs.iter().filter(|v| cmp.compare(v, v).is_some()).collect();
            placed.sort_by(|a, b| cmp.compare(a, b).unwrap_or(std::cmp::Ordering::Equal));
            let unplaced = vs.len() - placed.len();
            let pair = |c: Comparator| {
                c.min_max(vs.iter().map(|v| &v[..]))
                    .map(|(lo, hi)| {
                        obj([
                            ("min", stat_display(leaf, lo).into()),
                            ("max", stat_display(leaf, hi).into()),
                        ])
                    })
                    .unwrap_or(Json::Null)
            };
            obj([
                (
                    "sorted",
                    Json::Arr(
                        placed
                            .iter()
                            .map(|v| stat_display(leaf, v).into())
                            .collect(),
                    ),
                ),
                ("unplaced", unplaced.into()),
                ("nulls", nulls.into()),
                ("observed", pair(cmp)),
                (
                    "mistake",
                    cmp.mistake()
                        .map(|(wrong, what)| {
                            obj([
                                ("comparator", wrong.name().into()),
                                ("what", what.into()),
                                ("result", pair(wrong)),
                            ])
                        })
                        .unwrap_or(Json::Null),
                ),
            ])
        }
        None => Json::Null,
    };
    obj([
        ("ok", true.into()),
        ("created_by", md.created_by.clone().into()),
        ("column_orders", md.column_orders.is_some().into()),
        ("row_groups", row_groups),
        ("columns", columns),
        (
            "selected",
            obj([
                ("row_group", row_group.into()),
                ("column", column.into()),
                ("path", leaf.dotted_path().into()),
                ("order", cmp.order().name().into()),
                ("comparator", cmp.name().into()),
                (
                    "statistics_span",
                    chunk
                        .statistics
                        .as_ref()
                        .map(|s| Json::from(s.span))
                        .unwrap_or(Json::Null),
                ),
                ("fields", Json::Arr(fields)),
                (
                    "verdict",
                    match verdict {
                        Ok(b) => obj([
                            ("usable", true.into()),
                            ("source", source_name(b.source).into()),
                            ("min", stat_display(leaf, &b.min).into()),
                            ("max", stat_display(leaf, &b.max).into()),
                            ("min_exact", b.min_exact.into()),
                            ("max_exact", b.max_exact.into()),
                        ]),
                        Err(reason) => obj([("usable", false.into()), ("reason", reason.into())]),
                    },
                ),
                ("values", values_json),
            ]),
        ),
    ])
}

/// The comparisons `report::skipping` accepts, in the order the WASM interface numbers them.
pub const OPS: [&str; 8] = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];

/// Ch09's experiment: a condition on one column, and what the reader skips to answer
/// `SELECT *` with it. `mechanisms` is a bit set: 1 row group statistics, 2 Bloom filters,
/// 4 the page index.
pub fn skipping(file: &[u8], column: usize, op: &str, value: &str, mechanisms: u32) -> Json {
    use crate::column::read_column;
    use crate::prune::{plan, Mechanisms, Op, Predicate};
    use crate::schema::{build, leaves};

    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let md = match open_bytes(file) {
        Ok(md) => md,
        Err(e) => return fail(e),
    };
    let root = match build(&md.schema) {
        Ok(r) => r,
        Err(e) => return fail(e.to_string()),
    };
    let all = leaves(&root);
    let flat: Vec<&crate::schema::Leaf> =
        all.iter().filter(|l| l.max_repetition_level == 0).collect();
    let columns = Json::Arr(
        flat.iter()
            .map(|l| {
                obj([
                    ("column", l.column.into()),
                    ("path", l.dotted_path().into()),
                    (
                        "type",
                        crate::schema::physical_word(l.physical_type, l.type_length).into(),
                    ),
                ])
            })
            .collect(),
    );
    let with_columns = |mut j: Json| {
        if let Json::Obj(ref mut fields) = j {
            fields.push(("columns".into(), columns.clone()));
        }
        j
    };
    let Some(leaf) = flat.iter().find(|l| l.column == column) else {
        return with_columns(fail(format!("no column {column} that does not repeat")));
    };
    let op = match Op::parse(op) {
        Ok(op) => op,
        Err(e) => return with_columns(fail(e)),
    };
    let converted = md.schema[leaf.element].converted_type.clone();
    let p = match Predicate::new(leaf, converted.as_deref(), op, value) {
        Ok(p) => p,
        Err(e) => return with_columns(fail(e)),
    };
    let use_ = Mechanisms {
        statistics: mechanisms & 1 != 0,
        bloom: mechanisms & 2 != 0,
        page_index: mechanisms & 4 != 0,
    };
    let projection: Vec<usize> = flat.iter().map(|l| l.column).collect();
    let pl = match plan(file, &md, leaf, &p, &projection, use_) {
        Ok(pl) => pl,
        Err(e) => return with_columns(fail(e)),
    };
    let full = match plan(file, &md, leaf, &p, &projection, Mechanisms::NONE) {
        Ok(pl) => pl,
        Err(e) => return with_columns(fail(e)),
    };
    // The answer, by reading everything: how many rows match, and in which row groups.
    let mut matching = Vec::new();
    for rg in &md.row_groups {
        let n = match read_column(file, &rg.columns[leaf.column], leaf) {
            Ok(d) => d
                .triples
                .iter()
                .filter(|t| {
                    let v = t
                        .value
                        .as_ref()
                        .map(|v| v.to_plain_bytes(leaf.physical_type));
                    p.row_matches(v.as_deref())
                })
                .count(),
            Err(e) => return with_columns(fail(e.to_string())),
        };
        matching.push(n);
    }
    let path_of = |c: usize| all.get(c).map(|l| l.dotted_path()).unwrap_or_default();
    let groups = Json::Arr(
        pl.row_groups
            .iter()
            .map(|g| {
                let chunk = &md.row_groups[g.index].columns[leaf.column];
                // For equality, the Bloom filter probe in full, whether or not it decided.
                let probe = match (&p.value, p.op) {
                    (Some(x), Op::Eq) if use_.bloom => crate::bloom::read(file, chunk)
                        .ok()
                        .flatten()
                        .map(|f| {
                            let pr = f.probe(x);
                            obj([
                                ("hash", format!("{:016x}", pr.hash).into()),
                                ("block", pr.block.into()),
                                ("blocks", f.num_blocks().into()),
                                ("block_span", f.block_span(pr.block).into()),
                                (
                                    "bits",
                                    Json::Arr(
                                        pr.bits
                                            .iter()
                                            .map(|&(b, set)| {
                                                obj([("bit", b.into()), ("set", set.into())])
                                            })
                                            .collect(),
                                    ),
                                ),
                                ("may_contain", pr.may_contain.into()),
                            ])
                        })
                        .unwrap_or(Json::Null),
                    _ => Json::Null,
                };
                obj([
                    ("index", g.index.into()),
                    ("num_rows", g.num_rows.into()),
                    ("skipped", g.skipped.into()),
                    ("matching", matching[g.index].into()),
                    (
                        "steps",
                        Json::Arr(
                            g.steps
                                .iter()
                                .map(|(m, d)| {
                                    obj([
                                        ("mechanism", (*m).into()),
                                        ("skip", d.skip.into()),
                                        ("why", d.why.clone().into()),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                    ("bloom", probe),
                    (
                        "pages",
                        Json::Arr(
                            g.pages
                                .iter()
                                .map(|q| {
                                    obj([
                                        ("span", q.span.into()),
                                        ("rows", Json::Arr(vec![q.rows.0.into(), q.rows.1.into()])),
                                        ("skip", q.decision.skip.into()),
                                        ("why", q.decision.why.clone().into()),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                    (
                        "rows",
                        Json::Arr(
                            g.rows
                                .iter()
                                .map(|&(a, b)| Json::Arr(vec![a.into(), b.into()]))
                                .collect(),
                        ),
                    ),
                    (
                        "reads",
                        Json::Arr(
                            g.reads
                                .iter()
                                .map(|r| {
                                    obj([
                                        ("column", r.column.into()),
                                        ("path", path_of(r.column).into()),
                                        (
                                            "spans",
                                            Json::Arr(
                                                r.spans.iter().map(|s| (*s).into()).collect(),
                                            ),
                                        ),
                                        (
                                            "bytes",
                                            r.spans.iter().map(|s| s.len()).sum::<u64>().into(),
                                        ),
                                        ("pages_read", r.pages_read.into()),
                                        ("pages_total", r.pages_total.into()),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                    ("index_bytes", g.index_bytes.into()),
                ])
            })
            .collect(),
    );
    let condition = match &p.value {
        Some(_) => format!("{} {} {}", leaf.dotted_path(), op.symbol(), value.trim()),
        None => format!("{} {}", leaf.dotted_path(), op.symbol()),
    };
    obj([
        ("ok", true.into()),
        ("columns", columns),
        ("column", column.into()),
        ("condition", condition.into()),
        (
            "mechanisms",
            obj([
                ("statistics", use_.statistics.into()),
                ("bloom", use_.bloom.into()),
                ("page_index", use_.page_index.into()),
            ]),
        ),
        (
            "totals",
            obj([
                ("rows", md.num_rows.into()),
                ("rows_read", pl.rows_read().into()),
                ("rows_matching", matching.iter().sum::<usize>().into()),
                ("bytes_full_scan", full.bytes_read().into()),
                ("bytes_read", pl.bytes_read().into()),
                ("index_bytes", pl.index_bytes().into()),
            ]),
        ),
        ("row_groups", groups),
    ])
}

/// The leaf columns that do not repeat: the ones `scan` can return.
pub fn flat_columns(file: &[u8]) -> Result<Vec<usize>, String> {
    let md = open_bytes(file)?;
    let root = crate::schema::build(&md.schema).map_err(|e| e.to_string())?;
    Ok(crate::schema::leaves(&root)
        .iter()
        .filter(|l| l.max_repetition_level == 0)
        .map(|l| l.column)
        .collect())
}

/// Ch10's experiment: a query run against the file in the simulated object store, with every
/// request, when it ran and on which connection, and the rows it returned.
pub fn scan(
    file: &[u8],
    query: &crate::scan::Query,
    strategy: crate::scan::Strategy,
    model: NetworkModel,
) -> Json {
    use crate::scan::scan as run;
    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let columns = match open_bytes(file).and_then(|md| {
        let root = crate::schema::build(&md.schema).map_err(|e| e.to_string())?;
        Ok(crate::schema::leaves(&root)
            .iter()
            .filter(|l| l.max_repetition_level == 0)
            .map(|l| {
                obj([
                    ("column", l.column.into()),
                    ("path", l.dotted_path().into()),
                ])
            })
            .collect::<Vec<_>>())
    }) {
        Ok(c) => Json::Arr(c),
        Err(e) => return fail(e),
    };
    let r = match run(file, "data.parquet", query, strategy, model) {
        Ok(r) => r,
        Err(e) => {
            let mut j = fail(e);
            if let Json::Obj(ref mut f) = j {
                f.push(("columns".into(), columns));
            }
            return j;
        }
    };
    let after: Vec<&Request> = r
        .requests
        .iter()
        .filter(|q| q.why.starts_with("read the indexes") || q.why.starts_with("read the pages"))
        .collect();
    let (footer_bytes, row_groups) = match (
        parse_trailer(
            file[file.len() - 8..].try_into().unwrap(),
            file.len() as u64,
        ),
        open_bytes(file),
    ) {
        (Ok(t), Ok(md)) => (u64::from(t.footer_length), md.row_groups.len()),
        _ => (0, 0),
    };
    obj([
        ("ok", true.into()),
        ("columns", columns),
        ("file_size", file.len().into()),
        (
            "strategy",
            obj([
                ("footer", options_json(strategy.footer, model)),
                ("connections", strategy.connections.into()),
                ("coalesce_gap", strategy.coalesce_gap.into()),
                ("whole_chunks", strategy.whole_chunks.into()),
                ("statistics", strategy.mechanisms.statistics.into()),
                ("bloom", strategy.mechanisms.bloom.into()),
                ("page_index", strategy.mechanisms.page_index.into()),
            ]),
        ),
        (
            "totals",
            obj([
                ("requests", r.requests.len().into()),
                ("elapsed_us", r.elapsed_us.into()),
                ("bytes_fetched", r.bytes_fetched.into()),
                ("bytes_planned", r.bytes_planned.into()),
                ("rows_decoded", r.rows_decoded.into()),
                ("rows_matching", r.matches.len().into()),
                // What the query read once it had the footer: its indexes and pages.
                ("requests_after_footer", after.len().into()),
                (
                    "bytes_after_footer",
                    after.iter().map(|q| q.bytes_returned).sum::<u64>().into(),
                ),
                ("footer_bytes", footer_bytes.into()),
                ("row_groups", row_groups.into()),
            ]),
        ),
        ("requests", requests_json(&r.requests)),
        (
            "result",
            obj([
                (
                    "columns",
                    Json::Arr(r.column_names.iter().map(|c| c.clone().into()).collect()),
                ),
                (
                    "rows",
                    Json::Arr(r.rows.into_iter().map(Json::Arr).collect()),
                ),
            ]),
        ),
    ])
}

/// Ch12's experiment: `sql` answered from `file`, with every stage of the pipeline.
pub fn query(file: &[u8], sql: &str) -> Json {
    let a = match crate::engine::run(file, sql) {
        Ok(a) => a,
        Err(e) => return obj([("ok", false.into()), ("error", e.into())]),
    };
    let rows = |rows: &[Vec<crate::engine::Value>]| {
        Json::Arr(
            rows.iter()
                .map(|r| Json::Arr(r.iter().map(|v| v.to_json()).collect()))
                .collect(),
        )
    };
    let names = |c: &[String]| Json::Arr(c.iter().map(|n| n.clone().into()).collect());
    obj([
        ("ok", true.into()),
        ("columns", names(&a.columns)),
        ("rows", rows(&a.rows)),
        ("row_groups", a.row_groups.into()),
        ("row_groups_read", a.row_groups_read.into()),
        ("bytes_read", a.bytes_read.into()),
        (
            "stages",
            Json::Arr(
                a.stages
                    .iter()
                    .map(|s| {
                        obj([
                            ("name", s.name.clone().into()),
                            ("detail", s.detail.clone().into()),
                            ("rows_in", s.rows_in.into()),
                            ("rows_out", s.rows_out.into()),
                            ("columns", names(&s.columns)),
                            ("sample", rows(&s.sample)),
                        ])
                    })
                    .collect(),
            ),
        ),
    ])
}

/// The master key a key-metadata blob names, when it is JSON with a `masterKeyID`, as pyarrow's
/// is; otherwise its bytes as text or hex.
fn key_name(key_metadata: &[u8]) -> String {
    std::str::from_utf8(key_metadata)
        .ok()
        .and_then(|t| Json::parse(t).ok())
        .and_then(|j| {
            j.get("masterKeyID")
                .and_then(Json::as_str)
                .map(str::to_string)
        })
        .unwrap_or_else(|| hex(key_metadata))
}

/// Ch13's experiment: what a reader without keys can see in a file, and what it cannot. Every
/// "visible" item is something the reader decoded here; every "hidden" item is one it tried to
/// read and could not.
pub fn encryption(file: &[u8]) -> Json {
    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let item = |what: &str, span: Option<Span>, value: String| {
        obj([
            ("what", what.into()),
            ("span", span.map(Json::from).unwrap_or(Json::Null)),
            ("value", value.into()),
        ])
    };
    let mut visible = Vec::new();
    let mut hidden = Vec::new();
    let mut columns = Vec::new();
    let mode;
    if file.len() >= 4 && file[..4] == crate::crypto::MAGIC_ENCRYPTED {
        mode = "encrypted footer";
        let f = match crate::crypto::encrypted_footer(file) {
            Ok(f) => f,
            Err(e) => return fail(e),
        };
        visible.push(item(
            "That it is Parquet, with an encrypted footer",
            Some(Span::new(0, 4)),
            "PARE".into(),
        ));
        visible.push(item(
            "The encryption algorithm",
            Some(f.crypto_metadata.span),
            f.algorithm.clone(),
        ));
        if let Some(k) = &f.key_metadata {
            visible.push(item(
                "The footer key's name",
                Some(f.crypto_metadata.span),
                key_name(k),
            ));
        }
        visible.push(item(
            "The encrypted footer's size",
            Some(f.module.span),
            format!("{} bytes", f.module.span.len()),
        ));
        for what in [
            "The schema",
            "The number of rows",
            "Where any column is",
            "Any statistics",
            "Any values, even of columns not encrypted",
        ] {
            hidden.push(item(
                what,
                Some(f.module.ciphertext),
                "inside the encrypted footer".into(),
            ));
        }
    } else {
        let md = match open_bytes(file) {
            Ok(md) => md,
            Err(e) => return fail(e),
        };
        mode = if md.encryption_algorithm.is_some() {
            "plaintext footer"
        } else {
            "not encrypted"
        };
        if let Some(a) = &md.encryption_algorithm {
            visible.push(item(
                "The encryption algorithm",
                md.footer_signature,
                a.clone(),
            ));
        }
        if let Some(sig) = md.footer_signature {
            visible.push(item(
                "The footer's signature, which only the footer key can check",
                Some(sig),
                "28 bytes".into(),
            ));
        }
        let root = match crate::schema::build(&md.schema) {
            Ok(r) => r,
            Err(e) => return fail(e.to_string()),
        };
        let leaves = crate::schema::leaves(&root);
        visible.push(item(
            "The schema",
            None,
            leaves
                .iter()
                .map(|l| l.dotted_path())
                .collect::<Vec<_>>()
                .join(", "),
        ));
        visible.push(item("The number of rows", None, md.num_rows.to_string()));
        for leaf in &leaves {
            let chunks: Vec<&ColumnChunk> = md
                .row_groups
                .iter()
                .map(|rg| &rg.columns[leaf.column])
                .collect();
            let Some(first) = chunks.first() else {
                continue;
            };
            let path = leaf.dotted_path();
            let (key, sample, modules, error) = match &first.crypto {
                Some(c) => {
                    let key = match &c.key_metadata {
                        Some(k) if c.with_column_key => key_name(k),
                        _ => "the footer key".into(),
                    };
                    let modules = crate::crypto::chunk_modules(file, first.byte_range())
                        .map(|m| m.len())
                        .unwrap_or(0);
                    let error = crate::column::read_column(file, first, leaf)
                        .err()
                        .map(|e| e.to_string());
                    (Some(key), Vec::new(), modules, error)
                }
                None => {
                    let sample = crate::column::read_column(file, first, leaf)
                        .map(|d| {
                            d.triples
                                .iter()
                                .take(4)
                                .map(|t| {
                                    t.value
                                        .as_ref()
                                        .map(|v| {
                                            crate::logical::value_json(
                                                leaf.physical_type,
                                                leaf.logical_type.as_ref(),
                                                v,
                                            )
                                        })
                                        .unwrap_or(Json::Null)
                                })
                                .collect()
                        })
                        .unwrap_or_default();
                    (None, sample, 0, None)
                }
            };
            if key.is_none() && md.encryption_algorithm.is_some() {
                let shown: Vec<String> = sample.iter().map(|v| v.to_json()).collect();
                visible.push(item(
                    &format!("The values of {path}"),
                    Some(first.byte_range()),
                    format!("{}, …", shown.join(", ")),
                ));
                if let Some(s) = &first.statistics {
                    if let (Some(lo), Some(hi)) = (&s.min_value, &s.max_value) {
                        visible.push(item(
                            &format!("The statistics of {path}"),
                            Some(s.span),
                            format!("{} to {}", stat_display(leaf, lo), stat_display(leaf, hi)),
                        ));
                    }
                }
            }
            if let Some(k) = &key {
                hidden.push(item(
                    &format!("The values of {path}"),
                    Some(first.byte_range()),
                    error.clone().unwrap_or_default(),
                ));
                if first.statistics.is_none() {
                    hidden.push(item(
                        &format!("The statistics of {path}"),
                        first.crypto.as_ref().and_then(|c| c.encrypted_metadata),
                        "withheld from the plaintext footer".into(),
                    ));
                }
                visible.push(item(&format!("Which key protects {path}"), None, k.clone()));
            }
            columns.push(obj([
                ("path", path.into()),
                ("encrypted", key.is_some().into()),
                ("key", key.into()),
                ("span", first.byte_range().into()),
                ("statistics_visible", first.statistics.is_some().into()),
                ("modules", modules.into()),
                ("sample", Json::Arr(sample)),
            ]));
        }
    }
    obj([
        ("ok", true.into()),
        ("mode", mode.into()),
        ("visible", Json::Arr(visible)),
        ("hidden", Json::Arr(hidden)),
        ("columns", Json::Arr(columns)),
    ])
}

/// Ch14's experiment: `sql` over the table under `table/` in a store holding `objects`, with its
/// files found by `discovery`: every file considered, every request made, and the answer.
pub fn table(
    objects: Vec<(String, Vec<u8>)>,
    sql: &str,
    discovery: crate::table::Discovery,
    connections: usize,
    model: NetworkModel,
) -> Json {
    let mut store = MemoryStore::new();
    for (k, v) in objects {
        store.put(&k, v);
    }
    let a = match crate::table::query(store, "table/", sql, discovery, connections, model) {
        Ok(a) => a,
        Err(e) => return obj([("ok", false.into()), ("error", e.into())]),
    };
    let rows = |rows: &[Vec<crate::engine::Value>]| {
        Json::Arr(
            rows.iter()
                .map(|r| Json::Arr(r.iter().map(|v| v.to_json()).collect()))
                .collect(),
        )
    };
    obj([
        ("ok", true.into()),
        (
            "discovery",
            match discovery {
                crate::table::Discovery::List => "list",
                crate::table::Discovery::ListAndPrune => "list and prune",
                crate::table::Discovery::Log => "log",
            }
            .into(),
        ),
        (
            "files",
            Json::Arr(
                a.files
                    .iter()
                    .map(|f| {
                        obj([
                            ("key", f.key.clone().into()),
                            (
                                "partition",
                                Json::Arr(
                                    f.partition
                                        .iter()
                                        .map(|(k, v)| format!("{k}={v}").into())
                                        .collect(),
                                ),
                            ),
                            ("size", f.size.into()),
                            ("rows", f.stats.as_ref().map(|s| s.num_records).into()),
                            ("read", f.read.into()),
                            ("why", f.why.clone().into()),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("requests", requests_json(&a.requests)),
        (
            "totals",
            obj([
                ("requests", a.requests.len().into()),
                ("elapsed_us", a.elapsed_us.into()),
                ("bytes_fetched", a.bytes_fetched.into()),
                ("files", a.files.len().into()),
                (
                    "files_read",
                    a.files.iter().filter(|f| f.read).count().into(),
                ),
            ]),
        ),
        (
            "columns",
            Json::Arr(a.answer.columns.iter().map(|c| c.clone().into()).collect()),
        ),
        ("rows", rows(&a.answer.rows)),
        (
            "stages",
            Json::Arr(
                a.answer
                    .stages
                    .iter()
                    .map(|s| {
                        obj([
                            ("name", s.name.clone().into()),
                            ("detail", s.detail.clone().into()),
                            ("rows_in", s.rows_in.into()),
                            ("rows_out", s.rows_out.into()),
                        ])
                    })
                    .collect(),
            ),
        ),
    ])
}

/// ch15's experiment: an operation on snapshot `id` of the changing table under `changes/`.
/// Every file of the snapshot is listed, with whether the operation read it and why.
pub fn changes(
    objects: Vec<(String, Vec<u8>)>,
    id: &str,
    op: crate::changes::Operation,
    prefetch: u64,
    connections: usize,
    model: NetworkModel,
) -> Json {
    use crate::changes::{self, Operation};
    let mut store = MemoryStore::new();
    for (k, v) in objects {
        store.put(&k, v);
    }
    let prefix = "changes/";
    let fail = |e: String| obj([("ok", false.into()), ("error", e.into())]);
    let file = |path: &str, kind: &str, size: u64, rows: i64, read: bool, why: String| {
        obj([
            ("path", path.into()),
            ("kind", kind.into()),
            ("size", size.into()),
            ("rows", rows.into()),
            ("read", read.into()),
            ("why", why.into()),
        ])
    };
    let totals = |requests: &[Request], elapsed: u64, bytes: u64, rows: u64| {
        let mut phases: Vec<usize> = requests.iter().map(|r| r.phase).collect();
        phases.dedup();
        obj([
            ("requests", requests.len().into()),
            ("round_trips", phases.len().into()),
            ("bytes_fetched", bytes.into()),
            ("elapsed_us", elapsed.into()),
            ("rows_decoded", rows.into()),
        ])
    };
    let head = |s: &changes::Snapshot, name: &str| {
        obj([
            ("ok", true.into()),
            ("operation", name.into()),
            (
                "snapshot",
                obj([
                    ("id", s.id.clone().into()),
                    ("summary", s.summary.clone().into()),
                ]),
            ),
        ])
    };
    let join = |a: Json, rest: Vec<(&str, Json)>| match a {
        Json::Obj(mut kv) => {
            kv.extend(rest.into_iter().map(|(k, v)| (k.to_string(), v)));
            Json::Obj(kv)
        }
        other => other,
    };
    match op {
        Operation::Scan => {
            let r = match changes::scan_table(store, prefix, id, connections, model) {
                Ok(r) => r,
                Err(e) => return fail(e),
            };
            let s = &r.snapshot;
            let mut files: Vec<Json> = s
                .data_files
                .iter()
                .map(|f| {
                    let n = s.deletes_for(&f.path).len();
                    let why = match n {
                        0 => "read: a scan reads every data file".to_string(),
                        n => format!(
                            "read: a scan reads every data file; {n} delete file{} name{} it",
                            if n == 1 { "" } else { "s" },
                            if n == 1 { "s" } else { "" }
                        ),
                    };
                    file(&f.path, "data", f.file_size, f.record_count, true, why)
                })
                .collect();
            files.extend(s.delete_files.iter().map(|d| {
                file(
                    &d.path,
                    "delete",
                    d.file_size,
                    d.record_count,
                    true,
                    format!("read: it names rows of {}", d.data_file),
                )
            }));
            join(
                head(s, "scan"),
                vec![
                    ("files", Json::Arr(files)),
                    ("requests", requests_json(&r.requests)),
                    (
                        "totals",
                        totals(
                            &r.requests,
                            r.elapsed_us,
                            r.bytes_fetched,
                            r.rows_decoded as u64,
                        ),
                    ),
                    (
                        "answer",
                        obj([
                            ("live_rows", r.live_rows.into()),
                            ("sum_amount_cents", r.sum_amount_cents.into()),
                        ]),
                    ),
                ],
            )
        }
        Operation::Lookup(key) => {
            let r = match changes::lookup(store, prefix, id, key, prefetch, connections, model) {
                Ok(r) => r,
                Err(e) => return fail(e),
            };
            let s = &r.snapshot;
            let mut files: Vec<Json> = s
                .data_files
                .iter()
                .map(|f| {
                    let read = r.data_files.contains(&f.path);
                    let why = format!(
                        "{}: its {} runs from {} to {}",
                        if read { "opened" } else { "skipped" },
                        changes::KEY,
                        f.min_key,
                        f.max_key
                    );
                    file(&f.path, "data", f.file_size, f.record_count, read, why)
                })
                .collect();
            files.extend(s.delete_files.iter().map(|d| {
                let read = r.delete_files.contains(&d.path);
                let why = if read {
                    format!(
                        "read: it names rows of {}, which may hold the key",
                        d.data_file
                    )
                } else {
                    format!("skipped: it names rows of {}", d.data_file)
                };
                file(&d.path, "delete", d.file_size, d.record_count, read, why)
            }));
            // A key-value store's answer: one request for one row's bytes, taken as the share of
            // its file that one row occupies.
            let share = r
                .found
                .as_ref()
                .and_then(|(p, _)| s.data_files.iter().find(|f| &f.path == p))
                .or_else(|| s.data_files.iter().find(|f| r.data_files.contains(&f.path)))
                .map(|f| f.file_size.div_ceil(f.record_count.max(1) as u64))
                .unwrap_or(0);
            join(
                head(s, "lookup"),
                vec![
                    ("key", key.into()),
                    ("files", Json::Arr(files)),
                    ("requests", requests_json(&r.requests)),
                    (
                        "totals",
                        totals(&r.requests, r.elapsed_us, r.bytes_fetched, r.rows_decoded),
                    ),
                    (
                        "found",
                        match &r.found {
                            Some((path, pos)) => {
                                obj([("path", path.clone().into()), ("position", (*pos).into())])
                            }
                            None => Json::Null,
                        },
                    ),
                    ("deleted_by", r.deleted_by.clone().into()),
                    (
                        "row",
                        Json::Arr(
                            r.row
                                .iter()
                                .map(|(c, v)| {
                                    obj([("column", c.clone().into()), ("value", v.clone())])
                                })
                                .collect(),
                        ),
                    ),
                    (
                        "key_value",
                        obj([
                            ("bytes", share.into()),
                            ("elapsed_us", model.cost_us(share).into()),
                        ]),
                    ),
                ],
            )
        }
        Operation::Compact {
            target_rows,
            small_rows,
        } => {
            let mut t = TracingStore::with_connections(store, model, connections);
            let s = match changes::open(&mut t, prefix, id) {
                Ok(s) => s,
                Err(e) => return fail(e),
            };
            let plan = changes::plan_compaction(&s, target_rows, small_rows);
            let group_of = |p: &str| {
                plan.iter()
                    .position(|g| g.data_files.iter().chain(&g.delete_files).any(|x| x == p))
            };
            let mut files: Vec<Json> = s
                .data_files
                .iter()
                .map(|f| {
                    let live = s.live_rows(f);
                    let why = match group_of(&f.path) {
                        Some(g) => format!("rewritten in group {}: {live} live rows", g + 1),
                        None => format!("kept: {live} live rows, no deletes"),
                    };
                    file(
                        &f.path,
                        "data",
                        f.file_size,
                        f.record_count,
                        group_of(&f.path).is_some(),
                        why,
                    )
                })
                .collect();
            files.extend(s.delete_files.iter().map(|d| {
                let why = match group_of(&d.path) {
                    Some(g) => format!("read by group {}, then no longer needed", g + 1),
                    None => "kept".to_string(),
                };
                file(
                    &d.path,
                    "delete",
                    d.file_size,
                    d.record_count,
                    group_of(&d.path).is_some(),
                    why,
                )
            }));
            let groups = Json::Arr(
                plan.iter()
                    .map(|g| {
                        obj([
                            (
                                "data_files",
                                Json::Arr(g.data_files.iter().map(|p| p.clone().into()).collect()),
                            ),
                            (
                                "delete_files",
                                Json::Arr(
                                    g.delete_files.iter().map(|p| p.clone().into()).collect(),
                                ),
                            ),
                            ("rows_in", g.rows_in.into()),
                            ("rows_out", g.rows_out.into()),
                            ("bytes_in", g.bytes_in.into()),
                        ])
                    })
                    .collect(),
            );
            join(
                head(&s, "compact"),
                vec![
                    ("target_rows", target_rows.into()),
                    ("small_rows", small_rows.into()),
                    ("files", Json::Arr(files)),
                    ("requests", requests_json(&t.requests)),
                    (
                        "totals",
                        totals(&t.requests, t.elapsed_us(), t.bytes_returned(), 0),
                    ),
                    ("groups", groups),
                    (
                        "bytes_in",
                        plan.iter().map(|g| g.bytes_in).sum::<u64>().into(),
                    ),
                ],
            )
        }
    }
}
