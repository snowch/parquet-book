//! The schema: a tree, stored as a flat list (ch03).
//!
//! The footer's `schema` field is a list of `SchemaElement`s in depth-first order. The first is
//! the root, which names the whole record. A group element says how many children it has, and
//! they follow it immediately, each with its own subtree. A leaf has no children and a physical
//! type, and holds data: every leaf is one column, and every column chunk in the file belongs to
//! exactly one leaf.
//!
//! ```text
//! flat:   schema(3)  order_id  shipping(2)  city  postcode
//!
//! tree:   schema
//!         ├── order_id
//!         └── shipping
//!             ├── city
//!             └── postcode
//! ```
//!
//! Rebuilding the tree needs nothing but `num_children`. So does computing, for each leaf, the
//! largest definition and repetition levels its values can carry, which ch04 uses to decode them.

use std::fmt;

use crate::bytes::Span;
use crate::logical::LogicalType;
use crate::metadata::{PhysicalType, SchemaElement};

/// How many values a field has in each record.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Repetition {
    /// Exactly one. Never null.
    Required,
    /// Zero or one: the field may be null.
    Optional,
    /// Zero or more: the field is a list.
    Repeated,
}

impl Repetition {
    fn from_name(name: Option<&str>) -> Repetition {
        match name {
            Some("OPTIONAL") => Repetition::Optional,
            Some("REPEATED") => Repetition::Repeated,
            _ => Repetition::Required,
        }
    }

    pub fn word(&self) -> &'static str {
        match self {
            Repetition::Required => "required",
            Repetition::Optional => "optional",
            Repetition::Repeated => "repeated",
        }
    }
}

/// A node of the rebuilt tree.
#[derive(Clone, Debug, PartialEq)]
pub struct SchemaNode {
    /// Position in the footer's flat list.
    pub element: usize,
    pub name: String,
    pub repetition: Repetition,
    pub physical_type: Option<PhysicalType>,
    pub type_length: Option<i64>,
    pub logical_type: Option<LogicalType>,
    pub converted_type: Option<String>,
    pub field_id: Option<i64>,
    pub span: Span,
    pub children: Vec<SchemaNode>,
}

impl SchemaNode {
    pub fn is_leaf(&self) -> bool {
        self.children.is_empty() && self.physical_type.is_some()
    }
}

/// A leaf column, with everything a reader needs to decode its values.
#[derive(Clone, Debug, PartialEq)]
pub struct Leaf {
    /// Which column this is: its position among the leaves, and so among each row group's
    /// column chunks.
    pub column: usize,
    /// The names from the root's child down to the leaf.
    pub path: Vec<String>,
    /// The repetition of every field on the path, root excluded.
    pub repetitions: Vec<Repetition>,
    pub max_definition_level: u32,
    pub max_repetition_level: u32,
    pub element: usize,
    pub physical_type: PhysicalType,
    pub type_length: Option<i64>,
    pub logical_type: Option<LogicalType>,
}

impl Leaf {
    pub fn dotted_path(&self) -> String {
        self.path.join(".")
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SchemaError {
    Empty,
    /// A group claims more children than there are elements left.
    TooFewElements {
        group: String,
        element: usize,
    },
    /// Elements are left over after the root's subtree ends.
    TrailingElements {
        from: usize,
    },
    /// A childless element with no physical type: neither a leaf nor a group.
    NotALeaf {
        name: String,
        element: usize,
    },
}

impl fmt::Display for SchemaError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SchemaError::Empty => write!(f, "the schema has no elements, not even a root"),
            SchemaError::TooFewElements { group, element } => write!(
                f,
                "group {group:?} (element {element}) claims more children than the schema has elements"
            ),
            SchemaError::TrailingElements { from } => write!(
                f,
                "the root's subtree ends before the list does; elements from {from} belong to no one"
            ),
            SchemaError::NotALeaf { name, element } => write!(
                f,
                "element {element} ({name:?}) has no children and no physical type"
            ),
        }
    }
}

impl std::error::Error for SchemaError {}

/// Rebuild the tree from the footer's flat, depth-first list.
///
/// Read an element; if it says it has `n` children, the next `n` subtrees are its children, each
/// read the same way. The recursion consumes the list from the front, and the whole list must be
/// consumed by the root's subtree.
pub fn build(elements: &[SchemaElement]) -> Result<SchemaNode, SchemaError> {
    if elements.is_empty() {
        return Err(SchemaError::Empty);
    }
    let mut next = 0;
    let root = subtree(elements, &mut next)?;
    if next != elements.len() {
        return Err(SchemaError::TrailingElements { from: next });
    }
    Ok(root)
}

fn subtree(elements: &[SchemaElement], next: &mut usize) -> Result<SchemaNode, SchemaError> {
    let index = *next;
    let e = &elements[index];
    *next += 1;
    let n = e.num_children.unwrap_or(0).max(0) as usize;
    let mut children = Vec::with_capacity(n);
    for _ in 0..n {
        if *next >= elements.len() {
            return Err(SchemaError::TooFewElements {
                group: e.name.clone(),
                element: index,
            });
        }
        children.push(subtree(elements, next)?);
    }
    if index > 0 && n == 0 && e.physical_type.is_none() {
        return Err(SchemaError::NotALeaf {
            name: e.name.clone(),
            element: index,
        });
    }
    Ok(SchemaNode {
        element: index,
        name: e.name.clone(),
        repetition: Repetition::from_name(e.repetition.as_deref()),
        physical_type: e.physical_type,
        type_length: e.type_length,
        logical_type: e.logical_type.clone(),
        converted_type: e.converted_type.clone(),
        field_id: e.field_id,
        span: e.span,
        children,
    })
}

/// The largest definition and repetition levels a leaf's values can carry.
///
/// Walk the path from the root's child to the leaf. Every field that may be absent (optional or
/// repeated) adds one to the maximum definition level: a value is "defined to level d" when the
/// first d such fields are present. Every repeated field adds one to the maximum repetition level.
/// Required fields add nothing, because they are always there.
pub fn max_levels(path: &[Repetition]) -> (u32, u32) {
    let mut def = 0;
    let mut rep = 0;
    for r in path {
        match r {
            Repetition::Required => {}
            Repetition::Optional => def += 1,
            Repetition::Repeated => {
                def += 1;
                rep += 1;
            }
        }
    }
    (def, rep)
}

/// Every leaf of the tree, in column order.
pub fn leaves(root: &SchemaNode) -> Vec<Leaf> {
    fn walk(node: &SchemaNode, path: &mut Vec<(String, Repetition)>, out: &mut Vec<Leaf>) {
        for child in &node.children {
            path.push((child.name.clone(), child.repetition));
            if child.children.is_empty() {
                let repetitions: Vec<Repetition> = path.iter().map(|(_, r)| *r).collect();
                let (def, rep) = max_levels(&repetitions);
                out.push(Leaf {
                    column: out.len(),
                    path: path.iter().map(|(n, _)| n.clone()).collect(),
                    repetitions,
                    max_definition_level: def,
                    max_repetition_level: rep,
                    element: child.element,
                    physical_type: child.physical_type.unwrap_or(PhysicalType(-1)),
                    type_length: child.type_length,
                    logical_type: child.logical_type.clone(),
                });
            } else {
                walk(child, path, out);
            }
            path.pop();
        }
    }
    let mut out = Vec::new();
    walk(root, &mut Vec::new(), &mut out);
    out
}

/// The physical type as the schema notation writes it: `int64`, `binary`,
/// `fixed_len_byte_array(4)`.
pub fn physical_word(t: PhysicalType, type_length: Option<i64>) -> String {
    match t.0 {
        0 => "boolean".into(),
        1 => "int32".into(),
        2 => "int64".into(),
        3 => "int96".into(),
        4 => "float".into(),
        5 => "double".into(),
        6 => "binary".into(),
        7 => format!("fixed_len_byte_array({})", type_length.unwrap_or(0)),
        other => format!("type{other}"),
    }
}

/// The tree in the textual notation Parquet tools print, which comes from the Dremel paper:
///
/// ```text
/// message schema {
///   required int64 order_id;
///   optional group shipping {
///     optional binary city (STRING);
///   }
/// }
/// ```
pub fn to_text(root: &SchemaNode) -> String {
    fn line(node: &SchemaNode, depth: usize, out: &mut String) {
        let indent = "  ".repeat(depth);
        let annotation = node
            .logical_type
            .as_ref()
            .map(|l| format!(" ({l})"))
            .unwrap_or_default();
        if node.children.is_empty() {
            let t = node
                .physical_type
                .map(|p| physical_word(p, node.type_length))
                .unwrap_or_else(|| "group".into());
            out.push_str(&format!(
                "{indent}{} {t} {}{annotation};\n",
                node.repetition.word(),
                node.name
            ));
        } else {
            out.push_str(&format!(
                "{indent}{} group {}{annotation} {{\n",
                node.repetition.word(),
                node.name
            ));
            for c in &node.children {
                line(c, depth + 1, out);
            }
            out.push_str(&format!("{indent}}}\n"));
        }
    }
    let mut out = format!("message {} {{\n", root.name);
    for c in &root.children {
        line(c, 1, &mut out);
    }
    out.push_str("}\n");
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn el(
        name: &str,
        children: Option<i64>,
        rep: Option<&str>,
        physical: Option<i64>,
    ) -> SchemaElement {
        SchemaElement {
            name: name.into(),
            physical_type: physical.map(PhysicalType),
            type_length: None,
            repetition: rep.map(str::to_string),
            num_children: children,
            converted_type: None,
            logical_type: None,
            scale: None,
            precision: None,
            field_id: None,
            span: Span::new(0, 0),
        }
    }

    fn sample() -> Vec<SchemaElement> {
        vec![
            el("schema", Some(2), None, None),
            el("order_id", None, Some("REQUIRED"), Some(2)),
            el("items", Some(2), Some("REPEATED"), None),
            el("sku", None, Some("REQUIRED"), Some(6)),
            el("discounts", None, Some("REPEATED"), Some(1)),
        ]
    }

    #[test]
    fn the_flat_list_rebuilds_into_a_tree() {
        let root = build(&sample()).unwrap();
        assert_eq!(root.children.len(), 2);
        assert_eq!(root.children[1].children.len(), 2);
        let paths: Vec<String> = leaves(&root).iter().map(Leaf::dotted_path).collect();
        assert_eq!(paths, ["order_id", "items.sku", "items.discounts"]);
    }

    #[test]
    fn levels_count_the_fields_that_may_be_absent_or_repeated() {
        let root = build(&sample()).unwrap();
        let levels: Vec<(u32, u32)> = leaves(&root)
            .iter()
            .map(|l| (l.max_definition_level, l.max_repetition_level))
            .collect();
        assert_eq!(levels, [(0, 0), (1, 1), (2, 2)]);
    }

    #[test]
    fn a_group_that_claims_too_many_children_is_refused() {
        let mut s = sample();
        s[2].num_children = Some(3);
        assert!(matches!(
            build(&s),
            Err(SchemaError::TooFewElements { element: 2, .. })
        ));
    }

    #[test]
    fn elements_nobody_owns_are_refused() {
        let mut s = sample();
        s[0].num_children = Some(1);
        assert_eq!(build(&s), Err(SchemaError::TrailingElements { from: 2 }));
    }

    #[test]
    fn the_text_form_nests_groups() {
        let text = to_text(&build(&sample()).unwrap());
        assert!(text.starts_with("message schema {\n  required int64 order_id;\n"));
        assert!(text.contains("  repeated group items {\n    required binary sku;\n"));
    }
}
