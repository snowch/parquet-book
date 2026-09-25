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

fn structure_inner(file: &[u8]) -> Result<Json, String> {
    let size = file.len() as u64;
    if size < crate::format::MIN_FILE_LEN {
        return Err(format!("{size} bytes is too short to be a Parquet file"));
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
    top.push(region(
        "Footer",
        "footer",
        footer,
        "FileMetaData".into(),
        vec![annotate(&md.tree, "FileMetaData", "FileMetaData", None)],
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
