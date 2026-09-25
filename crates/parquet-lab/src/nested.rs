//! Nested data: repetition and definition levels, and records rebuilt from them (ch04).
//!
//! A column stores a flat sequence of values, but a record can hold nulls, lists, and lists of
//! structs holding lists. Parquet keeps the shape by storing two small integers beside every
//! value slot, as the Dremel paper describes:
//!
//! - the **definition level** `d` counts how many of the optional and repeated fields on the
//!   path are present. At the maximum, the value is there. Below it, the field at depth `d + 1`
//!   is the first one missing, which says whether the value is null, or its list empty, or its
//!   parent absent.
//! - the **repetition level** `r` says where a new element starts. Zero starts a new record.
//!   A higher level continues the record and starts a new element in the list whose repeated
//!   field has that repetition level.
//!
//! This module names each field on a leaf's path with the levels at which it appears, explains
//! any triple in those terms, and reassembles records from a column's triples.

use crate::column::Triple;
use crate::json::Json;
use crate::logical::{value_json, LogicalType};
use crate::schema::{Leaf, Repetition, SchemaNode};

/// One field on the path from the root to a leaf.
#[derive(Clone, Debug, PartialEq)]
pub struct PathField {
    pub name: String,
    pub repetition: Repetition,
    /// The definition level a value has when this field is present.
    pub def: u32,
    /// The repetition level that starts a new element of this field, if it is repeated; for other
    /// fields, the repetition level of the nearest repeated field above it.
    pub rep: u32,
    /// Annotated `LIST`: a group whose repeated child is the list itself.
    pub is_list: bool,
    /// How the book names this field: `items[].sku` rather than `items.list.element.sku`.
    pub label: String,
}

/// The fields on a leaf's path, with their levels.
pub fn path_fields(root: &SchemaNode, leaf: &Leaf) -> Vec<PathField> {
    let mut out: Vec<PathField> = Vec::new();
    let mut node = root;
    let (mut def, mut rep) = (0, 0);
    let mut label = String::new();
    let mut parent_is_list = false;
    let mut in_list_element = false;
    for name in &leaf.path {
        let Some(child) = node.children.iter().find(|c| &c.name == name) else {
            break;
        };
        match child.repetition {
            Repetition::Required => {}
            Repetition::Optional => def += 1,
            Repetition::Repeated => {
                def += 1;
                rep += 1;
            }
        }
        // Name the field the way a reader of the data would: a LIST's repeated group and its
        // element vanish into `[]`.
        if parent_is_list && child.repetition == Repetition::Repeated {
            label.push_str("[]");
            in_list_element = true;
        } else if in_list_element {
            in_list_element = false;
        } else {
            if !label.is_empty() {
                label.push('.');
            }
            label.push_str(&child.name);
        }
        let is_list = child.logical_type == Some(LogicalType::List);
        out.push(PathField {
            name: child.name.clone(),
            repetition: child.repetition,
            def,
            rep,
            is_list,
            label: label.clone(),
        });
        parent_is_list = is_list;
        node = child;
    }
    out
}

/// What a triple says, in words.
pub fn explain(fields: &[PathField], t: &Triple) -> String {
    let max_def = fields.last().map(|f| f.def).unwrap_or(0);
    let starts = if t.rep == 0 {
        "starts a new record".to_string()
    } else {
        match fields
            .iter()
            .find(|f| f.repetition == Repetition::Repeated && f.rep == t.rep)
        {
            Some(f) => format!("adds an element to `{}`", list_name(fields, f)),
            None => format!("repetition level {} matches no repeated field", t.rep),
        }
    };
    let defined = if t.def >= max_def {
        "the value is present".to_string()
    } else {
        // The first field whose presence would have raised the level past `d`.
        match fields.iter().position(|f| f.def > t.def) {
            Some(i) => {
                let f = &fields[i];
                if f.repetition == Repetition::Repeated {
                    format!("`{}` is an empty list", list_name(fields, f))
                } else if i > 0 && fields[i - 1].repetition == Repetition::Repeated {
                    format!(
                        "an element of `{}` is null",
                        list_name(fields, &fields[i - 1])
                    )
                } else {
                    format!("`{}` is null", f.label)
                }
            }
            None => format!("definition level {} is above the maximum", t.def),
        }
    };
    format!("{starts}; {defined}")
}

/// The name of the list a repeated field makes: the `LIST` group above it when there is one.
fn list_name(fields: &[PathField], repeated: &PathField) -> String {
    match fields.iter().position(|f| std::ptr::eq(f, repeated)) {
        Some(i) if i > 0 && fields[i - 1].is_list => fields[i - 1].label.clone(),
        _ => repeated.label.clone(),
    }
}

/// Rebuild each record's value for this one column: the record with only this leaf's path in it.
///
/// Records are split where `r == 0`. Within a record, each field's value is built from the
/// triples that belong to one instance of it:
///
/// - a repeated field's triples split into elements wherever `r` is at most its repetition
///   level; if the first triple's `d` says the field is absent, the list is empty;
/// - an optional field whose first triple's `d` says it is absent is null;
/// - a leaf's value is the one triple's value.
///
/// A `LIST`-annotated group becomes an array of its elements, as readers present it, and each
/// value is read through the leaf's logical type.
pub fn assemble(fields: &[PathField], leaf: &Leaf, triples: &[Triple]) -> Vec<Json> {
    let a = Assembler { fields, leaf };
    let mut records = Vec::new();
    let mut start = 0;
    for i in 1..=triples.len() {
        if i == triples.len() || triples[i].rep == 0 {
            if i > start {
                let value = a.field_value(0, &triples[start..i]);
                records.push(Json::Obj(vec![(fields[0].name.clone(), value)]));
            }
            start = i;
        }
    }
    records
}

struct Assembler<'a> {
    fields: &'a [PathField],
    leaf: &'a Leaf,
}

impl Assembler<'_> {
    /// The value of `fields[i]`, given the triples of one instance of its parent.
    fn field_value(&self, i: usize, triples: &[Triple]) -> Json {
        let fields = self.fields;
        let f = &fields[i];
        if f.repetition == Repetition::Repeated {
            if triples[0].def < f.def {
                return Json::Arr(vec![]);
            }
            let mut elements = Vec::new();
            let mut start = 0;
            for j in 1..=triples.len() {
                if j == triples.len() || triples[j].rep <= f.rep {
                    elements.push(self.element_value(i, &triples[start..j]));
                    start = j;
                }
            }
            return Json::Arr(elements);
        }
        if triples[0].def < f.def {
            return Json::Null;
        }
        if f.is_list && i + 1 < fields.len() {
            // A LIST group is its list: present it as the array, not as a struct holding one.
            return self.field_value(i + 1, triples);
        }
        self.element_value(i, triples)
    }

    /// One present instance of `fields[i]`: the value, or a struct of the next field.
    fn element_value(&self, i: usize, triples: &[Triple]) -> Json {
        let fields = self.fields;
        if i + 1 == fields.len() {
            return triples[0]
                .value
                .as_ref()
                .map(|v| value_json(self.leaf.physical_type, self.leaf.logical_type.as_ref(), v))
                .unwrap_or(Json::Null);
        }
        let next = &fields[i + 1];
        let parent_is_list = i > 0 && fields[i - 1].is_list;
        if parent_is_list && fields[i].repetition == Repetition::Repeated {
            // The repeated group of a LIST: its one child is the element, shown directly.
            return self.field_value(i + 1, triples);
        }
        Json::Obj(vec![(next.name.clone(), self.field_value(i + 1, triples))])
    }
}
