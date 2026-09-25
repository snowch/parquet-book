//! A minimal JSON writer, so the crate needs no dependencies.
//!
//! The browser, the command line and the book's figures all receive the implementation's
//! results as JSON. Writing it takes seventy lines; depending on a serialisation framework
//! would make `cargo build --offline` fail on a fresh clone, and the WASM file larger.
//!
//! Objects keep their keys in insertion order, so output is deterministic and diffs cleanly.

use crate::bytes::Span;

#[derive(Clone, Debug, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Int(i64),
    UInt(u64),
    Float(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

/// The largest integer a JavaScript number holds exactly: 2^53 - 1.
const MAX_SAFE: u64 = (1 << 53) - 1;

/// Build an object from `(key, value)` pairs.
pub fn obj<const N: usize>(pairs: [(&str, Json); N]) -> Json {
    Json::Obj(pairs.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}

impl Json {
    /// Add a key to an object. Panics on anything else, which would be a bug in this crate.
    pub fn with(mut self, key: &str, value: impl Into<Json>) -> Json {
        match &mut self {
            Json::Obj(pairs) => pairs.push((key.to_string(), value.into())),
            other => panic!("with() on a non-object: {other:?}"),
        }
        self
    }

    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Obj(pairs) => pairs.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn to_json(&self) -> String {
        let mut out = String::new();
        self.write(&mut out, None, 0);
        out
    }

    /// Indented output, for files a person will read and diff.
    pub fn to_json_pretty(&self) -> String {
        let mut out = String::new();
        self.write(&mut out, Some(2), 0);
        out.push('\n');
        out
    }

    fn write(&self, out: &mut String, indent: Option<usize>, depth: usize) {
        let newline = |out: &mut String, d: usize| {
            if let Some(n) = indent {
                out.push('\n');
                out.push_str(&" ".repeat(n * d));
            }
        };
        match self {
            Json::Null => out.push_str("null"),
            Json::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
            // JavaScript numbers are doubles, exact only up to 2^53. A larger integer is written
            // as a string, so the browser shows the value the reader computed rather than the
            // nearest double. The parity test in tests/test_wasm.py found this.
            Json::Int(v) if v.unsigned_abs() > MAX_SAFE => write_str(out, &v.to_string()),
            Json::UInt(v) if *v > MAX_SAFE => write_str(out, &v.to_string()),
            Json::Int(v) => out.push_str(&v.to_string()),
            Json::UInt(v) => out.push_str(&v.to_string()),
            Json::Float(v) if v.is_finite() => out.push_str(&format!("{v}")),
            Json::Float(_) => out.push_str("null"),
            Json::Str(s) => write_str(out, s),
            Json::Arr(items) => {
                out.push('[');
                for (i, item) in items.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    newline(out, depth + 1);
                    item.write(out, indent, depth + 1);
                }
                if !items.is_empty() {
                    newline(out, depth);
                }
                out.push(']');
            }
            Json::Obj(pairs) => {
                out.push('{');
                for (i, (k, v)) in pairs.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    newline(out, depth + 1);
                    write_str(out, k);
                    out.push(':');
                    if indent.is_some() {
                        out.push(' ');
                    }
                    v.write(out, indent, depth + 1);
                }
                if !pairs.is_empty() {
                    newline(out, depth);
                }
                out.push('}');
            }
        }
    }
}

impl Json {
    /// Parse JSON text. Enough of the grammar for the fixture manifests and the tests: objects,
    /// arrays, strings with escapes, numbers, `true`, `false` and `null`.
    pub fn parse(text: &str) -> Result<Json, String> {
        let mut p = Parser {
            s: text.as_bytes(),
            i: 0,
        };
        let v = p.value()?;
        p.ws();
        if p.i != p.s.len() {
            return Err(format!("trailing characters at {}", p.i));
        }
        Ok(v)
    }

    pub fn as_u64(&self) -> Option<u64> {
        match *self {
            Json::UInt(v) => Some(v),
            Json::Int(v) => u64::try_from(v).ok(),
            _ => None,
        }
    }

    pub fn as_i64(&self) -> Option<i64> {
        match *self {
            Json::Int(v) => Some(v),
            Json::UInt(v) => i64::try_from(v).ok(),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Json::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&Vec<Json>> {
        match self {
            Json::Arr(v) => Some(v),
            _ => None,
        }
    }
}

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
}

impl Parser<'_> {
    fn ws(&mut self) {
        while self.i < self.s.len() && self.s[self.i].is_ascii_whitespace() {
            self.i += 1;
        }
    }

    fn expect(&mut self, lit: &str) -> Result<(), String> {
        if self.s[self.i..].starts_with(lit.as_bytes()) {
            self.i += lit.len();
            Ok(())
        } else {
            Err(format!("expected {lit} at {}", self.i))
        }
    }

    fn value(&mut self) -> Result<Json, String> {
        self.ws();
        match self.s.get(self.i) {
            None => Err("unexpected end".into()),
            Some(b'{') => {
                self.i += 1;
                let mut pairs = Vec::new();
                self.ws();
                if self.s.get(self.i) == Some(&b'}') {
                    self.i += 1;
                    return Ok(Json::Obj(pairs));
                }
                loop {
                    self.ws();
                    let k = self.string()?;
                    self.ws();
                    self.expect(":")?;
                    pairs.push((k, self.value()?));
                    self.ws();
                    match self.s.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b'}') => {
                            self.i += 1;
                            return Ok(Json::Obj(pairs));
                        }
                        _ => return Err(format!("expected , or }} at {}", self.i)),
                    }
                }
            }
            Some(b'[') => {
                self.i += 1;
                let mut items = Vec::new();
                self.ws();
                if self.s.get(self.i) == Some(&b']') {
                    self.i += 1;
                    return Ok(Json::Arr(items));
                }
                loop {
                    items.push(self.value()?);
                    self.ws();
                    match self.s.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b']') => {
                            self.i += 1;
                            return Ok(Json::Arr(items));
                        }
                        _ => return Err(format!("expected , or ] at {}", self.i)),
                    }
                }
            }
            Some(b'"') => Ok(Json::Str(self.string()?)),
            Some(b't') => self.expect("true").map(|_| Json::Bool(true)),
            Some(b'f') => self.expect("false").map(|_| Json::Bool(false)),
            Some(b'n') => self.expect("null").map(|_| Json::Null),
            Some(_) => self.number(),
        }
    }

    fn string(&mut self) -> Result<String, String> {
        self.expect("\"")?;
        let mut out = String::new();
        loop {
            let c = *self.s.get(self.i).ok_or("unterminated string")?;
            self.i += 1;
            match c {
                b'"' => return Ok(out),
                b'\\' => {
                    let e = *self.s.get(self.i).ok_or("unterminated escape")?;
                    self.i += 1;
                    match e {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'u' => {
                            let hex = std::str::from_utf8(
                                self.s.get(self.i..self.i + 4).ok_or("short \\u")?,
                            )
                            .map_err(|e| e.to_string())?;
                            let code = u32::from_str_radix(hex, 16).map_err(|e| e.to_string())?;
                            self.i += 4;
                            out.push(char::from_u32(code).unwrap_or('\u{fffd}'));
                        }
                        other => return Err(format!("bad escape \\{}", other as char)),
                    }
                }
                _ => {
                    // Copy a whole UTF-8 sequence at once.
                    let start = self.i - 1;
                    let mut end = self.i;
                    while end < self.s.len() && (self.s[end] & 0xc0) == 0x80 {
                        end += 1;
                    }
                    out.push_str(
                        std::str::from_utf8(&self.s[start..end]).map_err(|e| e.to_string())?,
                    );
                    self.i = end;
                }
            }
        }
    }

    fn number(&mut self) -> Result<Json, String> {
        let start = self.i;
        while self.i < self.s.len()
            && matches!(
                self.s[self.i],
                b'-' | b'+' | b'.' | b'e' | b'E' | b'0'..=b'9'
            )
        {
            self.i += 1;
        }
        let text = std::str::from_utf8(&self.s[start..self.i]).map_err(|e| e.to_string())?;
        if let Ok(v) = text.parse::<u64>() {
            Ok(Json::UInt(v))
        } else if let Ok(v) = text.parse::<i64>() {
            Ok(Json::Int(v))
        } else {
            text.parse::<f64>()
                .map(Json::Float)
                .map_err(|_| format!("bad number {text:?} at {start}"))
        }
    }
}

fn write_str(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

impl From<bool> for Json {
    fn from(v: bool) -> Self {
        Json::Bool(v)
    }
}
impl From<i64> for Json {
    fn from(v: i64) -> Self {
        Json::Int(v)
    }
}
impl From<i32> for Json {
    fn from(v: i32) -> Self {
        Json::Int(i64::from(v))
    }
}
impl From<u64> for Json {
    fn from(v: u64) -> Self {
        Json::UInt(v)
    }
}
impl From<u32> for Json {
    fn from(v: u32) -> Self {
        Json::UInt(u64::from(v))
    }
}
impl From<u8> for Json {
    fn from(v: u8) -> Self {
        Json::UInt(u64::from(v))
    }
}
impl From<usize> for Json {
    fn from(v: usize) -> Self {
        Json::UInt(v as u64)
    }
}
impl From<f64> for Json {
    fn from(v: f64) -> Self {
        Json::Float(v)
    }
}
impl From<&str> for Json {
    fn from(v: &str) -> Self {
        Json::Str(v.to_string())
    }
}
impl From<String> for Json {
    fn from(v: String) -> Self {
        Json::Str(v)
    }
}
/// A span is written as `[start, end]`, half-open like the Rust value.
impl From<Span> for Json {
    fn from(s: Span) -> Self {
        Json::Arr(vec![Json::UInt(s.start), Json::UInt(s.end)])
    }
}
impl<T: Into<Json>> From<Option<T>> for Json {
    fn from(v: Option<T>) -> Self {
        v.map(Into::into).unwrap_or(Json::Null)
    }
}
impl<T: Into<Json>> From<Vec<T>> for Json {
    fn from(v: Vec<T>) -> Self {
        Json::Arr(v.into_iter().map(Into::into).collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strings_are_escaped() {
        assert_eq!(
            Json::from("a\"b\\c\n\u{1}").to_json(),
            r#""a\"b\\c\n\u0001""#
        );
    }

    #[test]
    fn objects_keep_their_key_order() {
        let j = obj([("z", 1i64.into()), ("a", Json::Null)]).with("m", vec![1u64, 2]);
        assert_eq!(j.to_json(), r#"{"z":1,"a":null,"m":[1,2]}"#);
    }

    #[test]
    fn parsing_round_trips_what_writing_produces() {
        let j = obj([
            ("s", "é \"q\" \n".into()),
            ("n", Json::Int(-3)),
            ("u", 7u64.into()),
            ("f", 1.5f64.into()),
            ("a", Json::Arr(vec![Json::Bool(true), Json::Null])),
            ("o", obj([])),
        ]);
        assert_eq!(Json::parse(&j.to_json()).unwrap(), j);
        assert_eq!(Json::parse(&j.to_json_pretty()).unwrap(), j);
        assert!(Json::parse("[1,").is_err());
        assert!(Json::parse("{} x").is_err());
    }

    #[test]
    fn integers_javascript_would_round_are_written_as_strings() {
        assert_eq!(Json::UInt(MAX_SAFE).to_json(), "9007199254740991");
        assert_eq!(Json::UInt(MAX_SAFE + 1).to_json(), "\"9007199254740992\"");
        assert_eq!(Json::Int(i64::MIN).to_json(), "\"-9223372036854775808\"");
    }

    #[test]
    fn spans_are_pairs_and_non_finite_floats_are_null() {
        assert_eq!(Json::from(Span::new(3, 9)).to_json(), "[3,9]");
        assert_eq!(Json::from(f64::NAN).to_json(), "null");
    }
}
