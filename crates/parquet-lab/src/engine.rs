//! A tiny query engine: SQL answered from Parquet bytes (ch12).
//!
//! Every earlier chapter built a piece of a reader. This module puts them under a query language,
//! small enough to read in full:
//!
//! ```text
//! SELECT *  |  item, item, ...          item: column, count(*), count(c), sum(c), min(c),
//! FROM name                                   max(c) or avg(c)
//! [WHERE condition AND condition ...]   condition: column op value, column IS [NOT] NULL
//! [GROUP BY column, ...]
//! [ORDER BY column [ASC|DESC], ...]
//! [LIMIT n]
//! ```
//!
//! A query runs as a pipeline of stages, each a plain loop over rows:
//!
//! 1. **Scan** reads the columns the query mentions. Row groups the footer's statistics rule out
//!    for any condition are skipped ([`crate::prune`]); the rest are decoded ([`crate::column`]).
//! 2. **Filter** keeps the rows every condition accepts, comparing in each column's own order
//!    ([`crate::stats`]).
//! 3. **Aggregate** groups rows and folds each group's values, when the query asks for it.
//! 4. **Sort** and **Limit** order and cut the result.
//!
//! Each stage records how many rows went in and came out, and a few of them, so the laboratory
//! can show the query at every step.

use std::cmp::Ordering;

use crate::json::Json;
use crate::metadata::FileMetaData;
use crate::prune::{against_bounds, Op, Predicate};
use crate::schema::{build, leaves, Leaf};
use crate::stats::bounds;

// ---- The language -------------------------------------------------------------------------

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Agg {
    Count,
    Sum,
    Min,
    Max,
    Avg,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Item {
    Star,
    Column(String),
    /// An aggregate; `None` is `count(*)`.
    Aggregate(Agg, Option<String>),
}

impl Item {
    /// The item as a result column is named: `country`, `count(*)`, `sum(amount_cents)`.
    pub fn name(&self) -> String {
        match self {
            Item::Star => "*".into(),
            Item::Column(c) => c.clone(),
            Item::Aggregate(a, arg) => format!(
                "{}({})",
                match a {
                    Agg::Count => "count",
                    Agg::Sum => "sum",
                    Agg::Min => "min",
                    Agg::Max => "max",
                    Agg::Avg => "avg",
                },
                arg.as_deref().unwrap_or("*")
            ),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Condition {
    pub column: String,
    pub op: Op,
    /// The literal as written, without quotes; empty for `IS NULL` and `IS NOT NULL`.
    pub value: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Select {
    pub items: Vec<Item>,
    pub from: String,
    pub conditions: Vec<Condition>,
    pub group_by: Vec<String>,
    /// Result column names, each ascending unless `true`.
    pub order_by: Vec<(String, bool)>,
    pub limit: Option<usize>,
}

#[derive(Clone, Debug, PartialEq)]
enum Token {
    Word(String),
    Number(String),
    Text(String),
    Symbol(String),
}

fn tokens(sql: &str) -> Result<Vec<Token>, String> {
    let chars: Vec<char> = sql.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c.is_whitespace() {
            i += 1;
        } else if c.is_ascii_alphabetic() || c == '_' {
            let start = i;
            while i < chars.len()
                && (chars[i].is_ascii_alphanumeric() || chars[i] == '_' || chars[i] == '.')
            {
                i += 1;
            }
            out.push(Token::Word(chars[start..i].iter().collect()));
        } else if c.is_ascii_digit()
            || (c == '-' && chars.get(i + 1).is_some_and(|d| d.is_ascii_digit()))
        {
            let start = i;
            i += 1;
            while i < chars.len() && (chars[i].is_ascii_digit() || chars[i] == '.') {
                i += 1;
            }
            out.push(Token::Number(chars[start..i].iter().collect()));
        } else if c == '\'' {
            let start = i + 1;
            i += 1;
            while i < chars.len() && chars[i] != '\'' {
                i += 1;
            }
            if i == chars.len() {
                return Err("a string is missing its closing quote".into());
            }
            out.push(Token::Text(chars[start..i].iter().collect()));
            i += 1;
        } else {
            let two: String = chars[i..(i + 2).min(chars.len())].iter().collect();
            let symbol = if ["<=", ">=", "!=", "<>"].contains(&two.as_str()) {
                two
            } else if "=<>(),*".contains(c) {
                c.to_string()
            } else {
                return Err(format!("unexpected character {c:?}"));
            };
            i += symbol.len();
            out.push(Token::Symbol(symbol));
        }
    }
    Ok(out)
}

struct Parser {
    tokens: Vec<Token>,
    at: usize,
}

impl Parser {
    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.at)
    }

    fn keyword(&mut self, k: &str) -> bool {
        match self.peek() {
            Some(Token::Word(w)) if w.eq_ignore_ascii_case(k) => {
                self.at += 1;
                true
            }
            _ => false,
        }
    }

    fn expect_keyword(&mut self, k: &str) -> Result<(), String> {
        if self.keyword(k) {
            Ok(())
        } else {
            Err(format!("expected {k}{}", self.here()))
        }
    }

    fn symbol(&mut self, s: &str) -> bool {
        match self.peek() {
            Some(Token::Symbol(x)) if x == s => {
                self.at += 1;
                true
            }
            _ => false,
        }
    }

    fn here(&self) -> String {
        match self.peek() {
            Some(Token::Word(w) | Token::Number(w) | Token::Symbol(w)) => format!(" at {w:?}"),
            Some(Token::Text(t)) => format!(" at '{t}'"),
            None => " at the end".into(),
        }
    }

    fn name(&mut self) -> Result<String, String> {
        match self.peek().cloned() {
            Some(Token::Word(w)) => {
                self.at += 1;
                Ok(w)
            }
            _ => Err(format!("expected a column name{}", self.here())),
        }
    }

    fn item(&mut self) -> Result<Item, String> {
        if self.symbol("*") {
            return Ok(Item::Star);
        }
        let word = self.name()?;
        let agg = match word.to_ascii_lowercase().as_str() {
            "count" => Some(Agg::Count),
            "sum" => Some(Agg::Sum),
            "min" => Some(Agg::Min),
            "max" => Some(Agg::Max),
            "avg" => Some(Agg::Avg),
            _ => None,
        };
        match agg {
            Some(a) if self.symbol("(") => {
                let arg = if a == Agg::Count && self.symbol("*") {
                    None
                } else {
                    Some(self.name()?)
                };
                if !self.symbol(")") {
                    return Err(format!("expected ){}", self.here()));
                }
                Ok(Item::Aggregate(a, arg))
            }
            _ => Ok(Item::Column(word)),
        }
    }

    fn condition(&mut self) -> Result<Condition, String> {
        let column = self.name()?;
        if self.keyword("is") {
            let not = self.keyword("not");
            self.expect_keyword("null")?;
            let op = if not { Op::IsNotNull } else { Op::IsNull };
            return Ok(Condition {
                column,
                op,
                value: String::new(),
            });
        }
        let op = match self.peek().cloned() {
            Some(Token::Symbol(s)) => {
                self.at += 1;
                Op::parse(if s == "<>" { "!=" } else { &s })?
            }
            _ => return Err(format!("expected a comparison{}", self.here())),
        };
        let value = match self.peek().cloned() {
            Some(Token::Number(n)) => n,
            Some(Token::Text(t)) => t,
            _ => return Err(format!("expected a value{}", self.here())),
        };
        self.at += 1;
        Ok(Condition { column, op, value })
    }

    fn list<T>(
        &mut self,
        mut one: impl FnMut(&mut Parser) -> Result<T, String>,
    ) -> Result<Vec<T>, String> {
        let mut out = vec![one(self)?];
        while self.symbol(",") {
            out.push(one(self)?);
        }
        Ok(out)
    }
}

/// Parse one `SELECT`.
pub fn parse(sql: &str) -> Result<Select, String> {
    let mut p = Parser {
        tokens: tokens(sql)?,
        at: 0,
    };
    p.expect_keyword("select")?;
    let items = p.list(Parser::item)?;
    p.expect_keyword("from")?;
    let from = p.name()?;
    let mut conditions = Vec::new();
    if p.keyword("where") {
        conditions.push(p.condition()?);
        while p.keyword("and") {
            conditions.push(p.condition()?);
        }
    }
    let mut group_by = Vec::new();
    if p.keyword("group") {
        p.expect_keyword("by")?;
        group_by = p.list(Parser::name)?;
    }
    let mut order_by = Vec::new();
    if p.keyword("order") {
        p.expect_keyword("by")?;
        order_by = p.list(|p| {
            let c = p.name()?;
            let desc = p.keyword("desc");
            if !desc {
                p.keyword("asc");
            }
            Ok((c, desc))
        })?;
    }
    let mut limit = None;
    if p.keyword("limit") {
        limit = match p.peek().cloned() {
            Some(Token::Number(n)) => {
                p.at += 1;
                Some(n.parse().map_err(|_| format!("LIMIT {n} is not a count"))?)
            }
            _ => return Err(format!("expected a number{}", p.here())),
        };
    }
    if p.at != p.tokens.len() {
        return Err(format!("unexpected{}", p.here()));
    }
    Ok(Select {
        items,
        from,
        conditions,
        group_by,
        order_by,
        limit,
    })
}

// ---- Values -------------------------------------------------------------------------------

/// A value in a result row.
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
}

impl Value {
    fn from_json(j: Json) -> Value {
        match j {
            Json::Null => Value::Null,
            Json::Bool(b) => Value::Bool(b),
            Json::Int(v) => Value::Int(v),
            Json::UInt(v) => Value::Int(v as i64),
            Json::Float(v) => Value::Float(v),
            Json::Str(s) => Value::Str(s),
            other => Value::Str(other.to_json()),
        }
    }

    pub fn to_json(&self) -> Json {
        match self {
            Value::Null => Json::Null,
            Value::Bool(b) => Json::Bool(*b),
            Value::Int(v) => Json::Int(*v),
            Value::Float(v) => Json::Float(*v),
            Value::Str(s) => Json::Str(s.clone()),
        }
    }

    fn number(&self) -> Option<f64> {
        match self {
            Value::Int(v) => Some(*v as f64),
            Value::Float(v) => Some(*v),
            _ => None,
        }
    }

    /// An order over every value, for sorting and grouping: nulls first, then numbers, then
    /// strings. Values of a column are all one kind, so the mixed cases only need to be fixed.
    pub fn order(&self, other: &Value) -> Ordering {
        use Value::*;
        let rank = |v: &Value| match v {
            Null => 0,
            Bool(_) => 1,
            Int(_) | Float(_) => 2,
            Str(_) => 3,
        };
        match (self, other) {
            (Int(a), Int(b)) => a.cmp(b),
            (Str(a), Str(b)) => a.as_bytes().cmp(b.as_bytes()),
            (Bool(a), Bool(b)) => a.cmp(b),
            (a, b) if rank(a) == 2 && rank(b) == 2 => a
                .number()
                .unwrap_or(0.0)
                .total_cmp(&b.number().unwrap_or(0.0)),
            (a, b) => rank(a).cmp(&rank(b)),
        }
    }
}

// ---- Running a query ----------------------------------------------------------------------

/// One stage of the pipeline, as the laboratory shows it.
#[derive(Clone, Debug, PartialEq)]
pub struct Stage {
    pub name: String,
    pub detail: String,
    pub rows_in: usize,
    pub rows_out: usize,
    pub columns: Vec<String>,
    /// The first few rows the stage produced.
    pub sample: Vec<Vec<Value>>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Answer {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<Value>>,
    pub stages: Vec<Stage>,
    pub row_groups_read: usize,
    pub row_groups: usize,
    pub bytes_read: u64,
}

const SAMPLE: usize = 5;

fn stage(
    name: &str,
    detail: String,
    rows_in: usize,
    columns: &[String],
    rows: &[Vec<Value>],
) -> Stage {
    Stage {
        name: name.into(),
        detail,
        rows_in,
        rows_out: rows.len(),
        columns: columns.to_vec(),
        sample: rows.iter().take(SAMPLE).cloned().collect(),
    }
}

/// An aggregate's running state for one group.
#[derive(Clone, Debug)]
enum Acc {
    Count(i64),
    Sum(Option<Value>),
    Min(Option<Value>),
    Max(Option<Value>),
    Avg(f64, i64),
}

impl Acc {
    fn new(a: Agg) -> Acc {
        match a {
            Agg::Count => Acc::Count(0),
            Agg::Sum => Acc::Sum(None),
            Agg::Min => Acc::Min(None),
            Agg::Max => Acc::Max(None),
            Agg::Avg => Acc::Avg(0.0, 0),
        }
    }

    /// Fold in one value. `None` is `count(*)`'s row, which counts whatever it holds.
    fn add(&mut self, v: Option<&Value>) {
        let v = match v {
            None => {
                if let Acc::Count(n) = self {
                    *n += 1;
                }
                return;
            }
            Some(Value::Null) => return, // aggregates skip nulls
            Some(v) => v,
        };
        match self {
            Acc::Count(n) => *n += 1,
            Acc::Sum(s) => {
                *s = Some(match (s.take(), v) {
                    (None, v) => v.clone(),
                    (Some(Value::Int(a)), Value::Int(b)) => Value::Int(a + b),
                    (Some(a), b) => {
                        Value::Float(a.number().unwrap_or(0.0) + b.number().unwrap_or(0.0))
                    }
                })
            }
            Acc::Min(m) => {
                if m.as_ref().map_or(true, |m| v.order(m) == Ordering::Less) {
                    *m = Some(v.clone());
                }
            }
            Acc::Max(m) => {
                if m.as_ref().map_or(true, |m| v.order(m) == Ordering::Greater) {
                    *m = Some(v.clone());
                }
            }
            Acc::Avg(s, n) => {
                *s += v.number().unwrap_or(0.0);
                *n += 1;
            }
        }
    }

    fn result(&self) -> Value {
        match self {
            Acc::Count(n) => Value::Int(*n),
            Acc::Sum(s) | Acc::Min(s) | Acc::Max(s) => s.clone().unwrap_or(Value::Null),
            Acc::Avg(_, 0) => Value::Null,
            Acc::Avg(s, n) => Value::Float(s / *n as f64),
        }
    }
}

/// Answer `sql` from `file`'s bytes.
pub fn run(file: &[u8], sql: &str) -> Result<Answer, String> {
    let q = parse(sql)?;
    let md: FileMetaData = crate::report::open_bytes(file)?;
    let root = build(&md.schema).map_err(|e| e.to_string())?;
    let flat: Vec<Leaf> = leaves(&root)
        .into_iter()
        .filter(|l| l.max_repetition_level == 0)
        .collect();
    let find = |name: &str| {
        flat.iter()
            .find(|l| l.dotted_path() == name)
            .ok_or(format!("no column {name}"))
    };

    // Every column the query mentions, in the order the schema has them.
    let mut mentioned: Vec<String> = Vec::new();
    for i in &q.items {
        match i {
            Item::Star => mentioned.extend(flat.iter().map(|l| l.dotted_path())),
            Item::Column(c) | Item::Aggregate(_, Some(c)) => mentioned.push(c.clone()),
            Item::Aggregate(_, None) => {}
        }
    }
    mentioned.extend(q.conditions.iter().map(|c| c.column.clone()));
    mentioned.extend(q.group_by.iter().cloned());
    let mut columns: Vec<&Leaf> = Vec::new();
    for name in &mentioned {
        let leaf = find(name)?;
        if !columns.iter().any(|l| l.column == leaf.column) {
            columns.push(leaf);
        }
    }
    columns.sort_by_key(|l| l.column);
    let names: Vec<String> = columns.iter().map(|l| l.dotted_path()).collect();
    let position = |name: &str| names.iter().position(|n| n == name);

    let predicates: Vec<(usize, Predicate)> = q
        .conditions
        .iter()
        .map(|c| {
            let leaf = find(&c.column)?;
            let conv = md.schema[leaf.element].converted_type.clone();
            Ok((
                position(&c.column).unwrap_or(0),
                Predicate::new(leaf, conv.as_deref(), c.op, &c.value)?,
            ))
        })
        .collect::<Result<_, String>>()?;

    // 1. Scan: skip the row groups any condition rules out, and decode the rest.
    let mut stages = Vec::new();
    let mut raw: Vec<Vec<Option<Vec<u8>>>> = Vec::new();
    let mut rows: Vec<Vec<Value>> = Vec::new();
    let (mut read, mut bytes, mut skipped_why) = (0, 0u64, Vec::new());
    for (g, rg) in md.row_groups.iter().enumerate() {
        // Skip the row group if any condition's comparison with its bounds rules it out.
        let ruled_out = q
            .conditions
            .iter()
            .zip(&predicates)
            .find_map(|(c, (_, p))| {
                let leaf = find(&c.column).ok()?;
                let chunk = &rg.columns[leaf.column];
                let s = chunk.statistics.as_ref()?;
                let type_order = md
                    .column_orders
                    .as_ref()
                    .and_then(|o| o.get(leaf.column))
                    .is_some_and(|o| o == "TYPE_ORDER");
                let b = bounds(s, p.comparator, type_order).ok();
                let d = against_bounds(
                    p,
                    b.as_ref().map(|b| (&b.min[..], &b.max[..])),
                    s.null_count,
                    chunk.num_values,
                );
                d.skip.then(|| {
                    format!(
                        "row group {g}: {} {} {}: {}",
                        c.column,
                        c.op.symbol(),
                        c.value,
                        d.why
                    )
                })
            });
        if let Some(why) = ruled_out {
            skipped_why.push(why);
            continue;
        }
        read += 1;
        let mut cols = Vec::new();
        for leaf in &columns {
            let chunk = &rg.columns[leaf.column];
            bytes += chunk.byte_range().len();
            let d = crate::column::read_column(file, chunk, leaf).map_err(|e| e.to_string())?;
            cols.push(
                d.triples
                    .iter()
                    .map(|t| {
                        let bytes = t
                            .value
                            .as_ref()
                            .map(|v| v.to_plain_bytes(leaf.physical_type));
                        let shown = t
                            .value
                            .as_ref()
                            .map(|v| {
                                crate::logical::value_json(
                                    leaf.physical_type,
                                    leaf.logical_type.as_ref(),
                                    v,
                                )
                            })
                            .unwrap_or(Json::Null);
                        (bytes, Value::from_json(shown))
                    })
                    .collect::<Vec<_>>(),
            );
        }
        for r in 0..rg.num_rows as usize {
            raw.push(cols.iter().map(|c| c[r].0.clone()).collect());
            rows.push(cols.iter().map(|c| c[r].1.clone()).collect());
        }
    }
    let scanned = md.num_rows as usize;
    stages.push(stage(
        "Scan",
        format!(
            "read {} of {} row groups, {bytes} bytes of column chunks{}",
            read,
            md.row_groups.len(),
            if skipped_why.is_empty() {
                String::new()
            } else {
                format!("; skipped {}", skipped_why.join("; "))
            }
        ),
        scanned,
        &names,
        &rows,
    ));

    // 2. Filter: every condition, in each column's own order.
    if !predicates.is_empty() {
        let before = rows.len();
        let keep: Vec<bool> = raw
            .iter()
            .map(|r| {
                predicates
                    .iter()
                    .all(|(i, p)| p.row_matches(r[*i].as_deref()))
            })
            .collect();
        let mut k = keep.iter();
        rows.retain(|_| *k.next().unwrap_or(&false));
        let text = q
            .conditions
            .iter()
            .map(|c| {
                if c.value.is_empty() {
                    format!("{} {}", c.column, c.op.symbol())
                } else {
                    format!("{} {} {}", c.column, c.op.symbol(), c.value)
                }
            })
            .collect::<Vec<_>>()
            .join(" and ");
        stages.push(stage("Filter", text, before, &names, &rows));
    }

    // 3. Aggregate, or project.
    let aggregating =
        !q.group_by.is_empty() || q.items.iter().any(|i| matches!(i, Item::Aggregate(..)));
    let out_names: Vec<String> = q
        .items
        .iter()
        .flat_map(|i| match i {
            Item::Star => names.clone(),
            other => vec![other.name()],
        })
        .collect();
    let before = rows.len();
    rows = if aggregating {
        let keys: Vec<usize> = q
            .group_by
            .iter()
            .map(|c| position(c).ok_or(format!("no column {c}")))
            .collect::<Result<_, _>>()?;
        for i in &q.items {
            match i {
                Item::Column(c) if !q.group_by.contains(c) => {
                    return Err(format!("{c} is neither grouped by nor aggregated"));
                }
                Item::Star => return Err("SELECT * cannot be aggregated".into()),
                _ => {}
            }
        }
        let aggs: Vec<(Agg, Option<usize>)> = q
            .items
            .iter()
            .filter_map(|i| match i {
                Item::Aggregate(a, arg) => Some((*a, arg.as_deref().and_then(position))),
                _ => None,
            })
            .collect();
        let mut groups: Vec<(Vec<Value>, Vec<Acc>)> = Vec::new();
        for r in &rows {
            let key: Vec<Value> = keys.iter().map(|&k| r[k].clone()).collect();
            let at = match groups.iter().position(|(k, _)| {
                k.iter()
                    .zip(&key)
                    .all(|(a, b)| a.order(b) == Ordering::Equal)
            }) {
                Some(at) => at,
                None => {
                    groups.push((key, aggs.iter().map(|(a, _)| Acc::new(*a)).collect()));
                    groups.len() - 1
                }
            };
            for (acc, (_, arg)) in groups[at].1.iter_mut().zip(&aggs) {
                acc.add(arg.map(|i| &r[i]));
            }
        }
        if groups.is_empty() && keys.is_empty() {
            groups.push((vec![], aggs.iter().map(|(a, _)| Acc::new(*a)).collect()));
        }
        let out: Vec<Vec<Value>> = groups
            .iter()
            .map(|(key, accs)| {
                let mut a = accs.iter();
                q.items
                    .iter()
                    .map(|i| match i {
                        Item::Column(c) => {
                            key[q.group_by.iter().position(|g| g == c).unwrap_or(0)].clone()
                        }
                        _ => a.next().map(Acc::result).unwrap_or(Value::Null),
                    })
                    .collect()
            })
            .collect();
        let by = if q.group_by.is_empty() {
            "all rows as one group".to_string()
        } else {
            format!("by {}", q.group_by.join(", "))
        };
        stages.push(stage("Aggregate", by, before, &out_names, &out));
        out
    } else {
        let idx: Vec<usize> = out_names
            .iter()
            .map(|n| position(n).ok_or(format!("no column {n}")))
            .collect::<Result<_, _>>()?;
        let out: Vec<Vec<Value>> = rows
            .iter()
            .map(|r| idx.iter().map(|&i| r[i].clone()).collect())
            .collect();
        stages.push(stage(
            "Project",
            out_names.join(", "),
            before,
            &out_names,
            &out,
        ));
        out
    };

    // 4. Sort and limit.
    if !q.order_by.is_empty() {
        let keys: Vec<(usize, bool)> = q
            .order_by
            .iter()
            .map(|(c, desc)| {
                out_names
                    .iter()
                    .position(|n| n == c)
                    .map(|i| (i, *desc))
                    .ok_or(format!(
                        "ORDER BY {c}: only result columns can be sorted by"
                    ))
            })
            .collect::<Result<_, _>>()?;
        rows.sort_by(|a, b| {
            keys.iter()
                .map(|&(i, desc)| {
                    let o = a[i].order(&b[i]);
                    if desc {
                        o.reverse()
                    } else {
                        o
                    }
                })
                .find(|o| *o != Ordering::Equal)
                .unwrap_or(Ordering::Equal)
        });
        let text = q
            .order_by
            .iter()
            .map(|(c, d)| {
                if *d {
                    format!("{c} descending")
                } else {
                    c.clone()
                }
            })
            .collect::<Vec<_>>()
            .join(", ");
        stages.push(stage("Sort", text, rows.len(), &out_names, &rows));
    }
    if let Some(n) = q.limit {
        let before = rows.len();
        rows.truncate(n);
        stages.push(stage(
            "Limit",
            format!("{n} rows"),
            before,
            &out_names,
            &rows,
        ));
    }
    Ok(Answer {
        columns: out_names,
        rows,
        stages,
        row_groups_read: read,
        row_groups: md.row_groups.len(),
        bytes_read: bytes,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_whole_language() {
        let q = parse(
            "select country, count(*), avg(amount) from t where amount >= 10 and note is not null \
             group by country order by country desc, count limit 3",
        )
        .unwrap();
        assert_eq!(q.items.len(), 3);
        assert_eq!(q.items[1].name(), "count(*)");
        assert_eq!(q.conditions[1].op, Op::IsNotNull);
        assert_eq!(
            q.order_by,
            vec![("country".into(), true), ("count".into(), false)]
        );
        assert_eq!(q.limit, Some(3));
        assert!(parse("select from t").is_err());
        assert!(parse("select a from t where b = ").is_err());
    }
}
