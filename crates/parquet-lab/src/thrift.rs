//! Apache Thrift's compact protocol, decoded without knowing the schema.
//!
//! Parquet serialises its footer and every page header with Thrift's compact protocol. The
//! protocol is self-delimiting: every field carries its own id and wire type, so a decoder can
//! walk a message it has no schema for. This one does exactly that, and records the span of
//! every field header and every value on the way.
//!
//! Names come later, from [`crate::parquet_thrift`], which knows that field 3 of a
//! `FileMetaData` is `num_rows`. Keeping the two apart is deliberate. The wire format is small
//! and regular; the Parquet schema is large and grows with every format release. A field this
//! decoder has never heard of still decodes, keeps its bytes, and shows up in the browser as
//! "field 17, a struct", which is how a reader stays forward-compatible.
//!
//! The encoding, in the order this module reads it:
//!
//! - A **field header** is one byte. The high four bits are the difference between this
//!   field's id and the previous one; the low four bits are the wire type. A difference of 0
//!   means the id follows as a zigzag varint.
//! - **Booleans** live in the header: wire type 1 is true, 2 is false. No value bytes follow.
//! - **Integers** of every width are zigzag varints. **Doubles** are eight bytes, little-endian.
//! - **Binary** (strings too) is a varint length and then the bytes.
//! - A **list** header is one byte: the size in the high four bits (15 means a varint size
//!   follows) and the element type in the low four.
//! - A **struct** is fields until a header byte of 0, the stop field.

use std::fmt;

use crate::bytes::{ByteReader, BytesError, Span};

/// The compact protocol's wire types.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WireType {
    BoolTrue,
    BoolFalse,
    Byte,
    I16,
    I32,
    I64,
    Double,
    Binary,
    List,
    Set,
    Map,
    Struct,
    Uuid,
}

impl WireType {
    pub fn from_nibble(n: u8) -> Option<WireType> {
        Some(match n {
            1 => WireType::BoolTrue,
            2 => WireType::BoolFalse,
            3 => WireType::Byte,
            4 => WireType::I16,
            5 => WireType::I32,
            6 => WireType::I64,
            7 => WireType::Double,
            8 => WireType::Binary,
            9 => WireType::List,
            10 => WireType::Set,
            11 => WireType::Map,
            12 => WireType::Struct,
            13 => WireType::Uuid,
            _ => return None,
        })
    }

    pub fn name(&self) -> &'static str {
        match self {
            WireType::BoolTrue | WireType::BoolFalse => "bool",
            WireType::Byte => "i8",
            WireType::I16 => "i16",
            WireType::I32 => "i32",
            WireType::I64 => "i64",
            WireType::Double => "double",
            WireType::Binary => "binary",
            WireType::List => "list",
            WireType::Set => "set",
            WireType::Map => "map",
            WireType::Struct => "struct",
            WireType::Uuid => "uuid",
        }
    }
}

/// A decoded value, with the bytes it came from.
#[derive(Clone, Debug, PartialEq)]
pub struct Node {
    pub span: Span,
    pub value: Value,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Bool(bool),
    Int(i64),
    Double(f64),
    Binary(Vec<u8>),
    List(Vec<Node>),
    Map(Vec<(Node, Node)>),
    Struct(Struct),
}

/// One field of a struct: its id, its wire type, the span of its header, and its value.
#[derive(Clone, Debug, PartialEq)]
pub struct Field {
    pub id: i16,
    pub wire: WireType,
    /// The header byte, plus the id varint when the delta did not fit in four bits.
    pub header: Span,
    pub node: Node,
}

impl Field {
    /// Everything this field occupies: header and value together.
    pub fn span(&self) -> Span {
        Span::new(self.header.start, self.node.span.end.max(self.header.end))
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Struct {
    pub fields: Vec<Field>,
}

impl Struct {
    pub fn field(&self, id: i16) -> Option<&Field> {
        self.fields.iter().find(|f| f.id == id)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ThriftError {
    Bytes(BytesError),
    UnknownWireType { nibble: u8, offset: u64 },
    TooDeep { offset: u64 },
    NegativeLength { offset: u64 },
}

impl fmt::Display for ThriftError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ThriftError::Bytes(e) => write!(f, "{e}"),
            ThriftError::UnknownWireType { nibble, offset } => {
                write!(f, "unknown Thrift wire type {nibble} at offset {offset}")
            }
            ThriftError::TooDeep { offset } => {
                write!(f, "structures nested too deeply at offset {offset}")
            }
            ThriftError::NegativeLength { offset } => {
                write!(f, "negative length at offset {offset}")
            }
        }
    }
}

impl std::error::Error for ThriftError {}

impl From<BytesError> for ThriftError {
    fn from(e: BytesError) -> Self {
        ThriftError::Bytes(e)
    }
}

/// How deep structs and lists may nest. Parquet's deepest is about six; a corrupt or hostile
/// footer should hit this long before it exhausts the stack.
const MAX_DEPTH: usize = 64;

/// Decode one struct, starting at the reader's position, up to and including its stop byte.
pub fn read_struct(r: &mut ByteReader) -> Result<Node, ThriftError> {
    read_struct_at_depth(r, 0)
}

fn read_struct_at_depth(r: &mut ByteReader, depth: usize) -> Result<Node, ThriftError> {
    if depth > MAX_DEPTH {
        return Err(ThriftError::TooDeep { offset: r.offset() });
    }
    let start = r.offset();
    let mut fields = Vec::new();
    let mut last_id: i16 = 0;
    loop {
        let header_start = r.offset();
        let byte = r.read_u8()?;
        if byte == 0 {
            break; // the stop field
        }
        let delta = byte >> 4;
        let nibble = byte & 0x0f;
        let wire = WireType::from_nibble(nibble).ok_or(ThriftError::UnknownWireType {
            nibble,
            offset: header_start,
        })?;
        let id = if delta == 0 {
            r.read_zigzag()? as i16
        } else {
            last_id + i16::from(delta)
        };
        last_id = id;
        let header = Span::new(header_start, r.offset());
        let node = match wire {
            // A field's boolean is its header's type nibble. It has no bytes of its own, so its
            // span is the header.
            WireType::BoolTrue => Node {
                span: header,
                value: Value::Bool(true),
            },
            WireType::BoolFalse => Node {
                span: header,
                value: Value::Bool(false),
            },
            _ => read_value(r, wire, depth + 1)?,
        };
        fields.push(Field {
            id,
            wire,
            header,
            node,
        });
    }
    Ok(Node {
        span: Span::new(start, r.offset()),
        value: Value::Struct(Struct { fields }),
    })
}

fn read_value(r: &mut ByteReader, wire: WireType, depth: usize) -> Result<Node, ThriftError> {
    let start = r.offset();
    let value = match wire {
        // Inside a list a boolean has no header to hide in, so it takes a byte: 1 is true.
        WireType::BoolTrue | WireType::BoolFalse => Value::Bool(r.read_u8()? == 1),
        WireType::Byte => Value::Int(i64::from(r.read_u8()? as i8)),
        WireType::I16 | WireType::I32 | WireType::I64 => Value::Int(r.read_zigzag()?),
        WireType::Double => Value::Double(f64::from_bits(r.read_le_u64()?)),
        WireType::Binary => {
            let len = r.read_uleb128()? as usize;
            let (bytes, _) = r.read_bytes(len)?;
            Value::Binary(bytes.to_vec())
        }
        WireType::Uuid => Value::Binary(r.read_bytes(16)?.0.to_vec()),
        WireType::List | WireType::Set => {
            let header = r.read_u8()?;
            let size = match header >> 4 {
                15 => r.read_uleb128()? as usize,
                small => usize::from(small),
            };
            let nibble = header & 0x0f;
            let elem = WireType::from_nibble(nibble).ok_or(ThriftError::UnknownWireType {
                nibble,
                offset: start,
            })?;
            let mut items = Vec::with_capacity(size.min(4096));
            for _ in 0..size {
                items.push(read_element(r, elem, depth)?);
            }
            Value::List(items)
        }
        WireType::Map => {
            let size = r.read_uleb128()? as usize;
            let mut entries = Vec::with_capacity(size.min(4096));
            if size > 0 {
                let types = r.read_u8()?;
                let (kn, vn) = (types >> 4, types & 0x0f);
                let k = WireType::from_nibble(kn).ok_or(ThriftError::UnknownWireType {
                    nibble: kn,
                    offset: start,
                })?;
                let v = WireType::from_nibble(vn).ok_or(ThriftError::UnknownWireType {
                    nibble: vn,
                    offset: start,
                })?;
                for _ in 0..size {
                    entries.push((read_element(r, k, depth)?, read_element(r, v, depth)?));
                }
            }
            Value::Map(entries)
        }
        WireType::Struct => return read_struct_at_depth(r, depth),
    };
    Ok(Node {
        span: Span::new(start, r.offset()),
        value,
    })
}

fn read_element(r: &mut ByteReader, wire: WireType, depth: usize) -> Result<Node, ThriftError> {
    if depth > MAX_DEPTH {
        return Err(ThriftError::TooDeep { offset: r.offset() });
    }
    read_value(r, wire, depth + 1)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn decode(bytes: &[u8]) -> Struct {
        let mut r = ByteReader::new(bytes, 0);
        match read_struct(&mut r).unwrap().value {
            Value::Struct(s) => s,
            other => panic!("not a struct: {other:?}"),
        }
    }

    #[test]
    fn a_field_header_packs_the_id_delta_and_the_type() {
        // 0x15 = delta 1, type 5 (i32); 0x04 is zigzag for 2. Then a stop byte.
        let s = decode(&[0x15, 0x04, 0x00]);
        assert_eq!(s.fields.len(), 1);
        let f = &s.fields[0];
        assert_eq!((f.id, f.wire), (1, WireType::I32));
        assert_eq!(f.header, Span::new(0, 1));
        assert_eq!(f.node.span, Span::new(1, 2));
        assert_eq!(f.node.value, Value::Int(2));
    }

    #[test]
    fn deltas_accumulate_from_the_previous_field() {
        // field 1 (i32 = 1), then delta 2 -> field 3 (i64 = -1).
        let s = decode(&[0x15, 0x02, 0x26, 0x01, 0x00]);
        assert_eq!(s.fields[1].id, 3);
        assert_eq!(s.fields[1].node.value, Value::Int(-1));
    }

    #[test]
    fn a_zero_delta_means_the_id_follows_as_a_varint() {
        // delta 0, type 5; id zigzag 0x28 = 20; value 0x02 = 1.
        let s = decode(&[0x05, 0x28, 0x02, 0x00]);
        assert_eq!(s.fields[0].id, 20);
        assert_eq!(s.fields[0].header, Span::new(0, 2));
    }

    #[test]
    fn booleans_live_in_the_header() {
        let s = decode(&[0x11, 0x12, 0x00]);
        assert_eq!(s.fields[0].node.value, Value::Bool(true));
        assert_eq!(s.fields[1].node.value, Value::Bool(false));
        assert_eq!(s.fields[1].node.span, s.fields[1].header);
    }

    #[test]
    fn binary_is_a_length_then_bytes() {
        let s = decode(&[0x18, 0x02, b'U', b'K', 0x00]);
        assert_eq!(s.fields[0].node.value, Value::Binary(b"UK".to_vec()));
        assert_eq!(s.fields[0].node.span, Span::new(1, 4));
    }

    #[test]
    fn a_list_header_packs_the_size_and_element_type() {
        // field 1, list; 0x35 = three i32s: 0, -1, 1.
        let s = decode(&[0x19, 0x35, 0x00, 0x01, 0x02, 0x00]);
        match &s.fields[0].node.value {
            Value::List(items) => {
                let ints: Vec<_> = items.iter().map(|n| n.value.clone()).collect();
                assert_eq!(ints, [Value::Int(0), Value::Int(-1), Value::Int(1)]);
            }
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn nested_structs_carry_their_own_stop_byte() {
        // field 1: struct { field 1: i32 = 3 }, then field 2: i32 = 4.
        let s = decode(&[0x1c, 0x15, 0x06, 0x00, 0x15, 0x08, 0x00]);
        assert_eq!(s.fields[0].node.span, Span::new(1, 4));
        assert_eq!(s.fields[1].id, 2);
    }

    #[test]
    fn truncated_input_is_an_error_with_an_offset() {
        let mut r = ByteReader::new(&[0x18, 0x05, b'a'], 500);
        let err = read_struct(&mut r).unwrap_err();
        assert_eq!(
            err,
            ThriftError::Bytes(BytesError::UnexpectedEnd {
                offset: 502,
                wanted: 5
            })
        );
    }

    #[test]
    fn unknown_wire_types_are_refused() {
        let mut r = ByteReader::new(&[0x1e], 0);
        assert!(matches!(
            read_struct(&mut r),
            Err(ThriftError::UnknownWireType { nibble: 14, .. })
        ));
    }
}
