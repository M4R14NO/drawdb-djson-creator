#!/usr/bin/env python3
"""
sql_to_djson.py — Convert SQL DDL to Axon Ivy 12 d.json dataclass files.

Usage (multi mode — one file per CREATE TABLE):
    python sql_to_djson.py input.sql --namespace com.example.entities --output ./out/
    python sql_to_djson.py input.sql --namespace com.example.entities --prefix History --output ./out/
    python sql_to_djson.py input.sql --namespace com.example.entities --useDefaultId --output ./out/

Usage (single mode — exactly one CREATE TABLE, extra overrides available):
    python sql_to_djson.py input.sql --namespace com.example.entities --single
    python sql_to_djson.py input.sql --namespace com.example.entities --single --tableName my_table
    python sql_to_djson.py input.sql --namespace com.example.entities --single --tableName my_table --prefix History
    python sql_to_djson.py input.sql --namespace com.example.entities --single --useDefaultId
"""

import re
import json
import argparse
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

SQL_TYPE_MAP = {
    # integers
    "int": "Integer",
    "int2": "Integer",
    "int4": "Integer",
    "int8": "Long",
    "integer": "Integer",
    "bigint": "Long",
    "smallint": "Integer",
    "serial": "Integer",
    "bigserial": "Long",
    # strings
    "varchar": "String",
    "text": "String",
    "char": "String",
    "character varying": "String",
    "uuid": "String",
    # boolean
    "boolean": "Boolean",
    "bool": "Boolean",
    # date / time
    "date": "java.util.Date",
    "datetime": "java.util.Date",
    "timestamp": "java.util.Date",
    "timestamptz": "java.util.Date",
    "timestamp with time zone": "java.util.Date",
    "timestamp without time zone": "java.util.Date",
    # numeric
    "numeric": "java.math.BigDecimal",
    "decimal": "java.math.BigDecimal",
    "float4": "Float",
    "float8": "Double",
    "real": "Float",
    "double precision": "Double",
}

UNKNOWN_TYPE_WARNINGS: list[tuple[str, str, str]] = []


def map_sql_type(sql_type: str, table: str, col: str) -> str:
    key_base = re.sub(r"\s*\(.*\)", "", sql_type.lower().strip()).strip()
    if key_base in SQL_TYPE_MAP:
        return SQL_TYPE_MAP[key_base]
    UNKNOWN_TYPE_WARNINGS.append((table, col, sql_type))
    return "String"


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def strip_quotes(s: str) -> str:
    return s.strip().strip('"').strip("'").strip("`")


def to_pascal(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def simple_name(table: str, prefix: Optional[str]) -> str:
    return f"{prefix}{to_pascal(table)}" if prefix else to_pascal(table)


def build_table_name(sql_table: str, prefix: Optional[str], override: Optional[str]) -> Optional[str]:
    """
    Returns the entity tableName string, or None if it should be omitted.
    Used only in single mode — multi mode always has a tableName.
    """
    base = override if override else None
    if prefix and base:
        return f"{prefix.lower()}_{base}"
    if prefix:
        return f"{prefix.lower()}_{sql_table}"
    if base:
        return base
    return None  # no prefix, no override → omit tableName


def seq_name(effective_tbl: str) -> str:
    return f"{effective_tbl}_sequence"


def assoc_type(namespace: str, table: str, prefix: Optional[str]) -> str:
    return f"{namespace}.{simple_name(table, prefix)}"


def pluralize_camel(name: str) -> str:
    if name.endswith("e"):
        return name + "n"
    if name.endswith("s"):
        return name + "e"
    return name + "en"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ColumnInfo:
    name: str
    sql_type: str
    is_pk: bool = False
    is_unique: bool = False
    is_not_null: bool = False
    is_identity: bool = False
    sequence_name: Optional[str] = None


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    inline_fks: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class AlterFk:
    src_table: str
    src_col: str
    ref_table: str
    ref_col: str


# ---------------------------------------------------------------------------
# SQL Parser
# ---------------------------------------------------------------------------

def normalize_sql(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def split_statements(sql: str) -> list[str]:
    stmts, depth, buf = [], 0, []
    for ch in sql:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
        else:
            buf.append(ch)
    if last := "".join(buf).strip():
        stmts.append(last)
    return stmts


def parse_column(col_def: str, table_name: str) -> Optional[ColumnInfo]:
    col_def = col_def.strip()
    if not col_def:
        return None
    upper = col_def.upper().lstrip()
    if re.match(r"(PRIMARY\s+KEY|UNIQUE|CHECK|CONSTRAINT\s+\w+\s+(PRIMARY|UNIQUE|CHECK))", upper):
        return None
    if re.match(r"(CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY", upper):
        return None

    m = re.match(r'"?(\w+)"?\s+(.*)', col_def, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    col_name, rest = m.group(1), m.group(2)

    is_identity = bool(re.search(r"GENERATED\s+(BY\s+DEFAULT|ALWAYS)\s+AS\s+IDENTITY", rest, re.IGNORECASE))

    seq_match = re.search(r"DEFAULT\s+nextval\s*\(\s*'([^']+)'", rest, re.IGNORECASE)
    seq = seq_match.group(1).split("::")[0].strip().strip("'\"") if seq_match else None

    type_match = re.match(
        r"([\w\s]+?)(?:\s*\([\d,\s]+\))?\s*(?:DEFAULT|GENERATED|NOT|NULL|PRIMARY|UNIQUE|REFERENCES|$)",
        rest, re.IGNORECASE)
    sql_type = type_match.group(1).strip() if type_match else rest.split()[0]
    len_match = re.match(r"([\w]+)\s*\(\s*\d+\s*\)", rest.strip(), re.IGNORECASE)
    if len_match:
        sql_type = len_match.group(1)

    return ColumnInfo(
        name=col_name,
        sql_type=sql_type,
        is_pk=bool(re.search(r"PRIMARY\s+KEY", rest, re.IGNORECASE)),
        is_unique=bool(re.search(r"\bUNIQUE\b", rest, re.IGNORECASE)),
        is_not_null=bool(re.search(r"NOT\s+NULL", rest, re.IGNORECASE)),
        is_identity=is_identity,
        sequence_name=seq,
    )


def parse_create_table(stmt: str) -> Optional[TableInfo]:
    m = re.match(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(\w+)\"?\s*\((.*)\)\s*$", stmt, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    table_name, body = m.group(1), m.group(2)

    parts, depth, buf = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())

    table = TableInfo(name=table_name)
    pk_cols: list[str] = []

    for part in parts:
        pk_m = re.match(r"(?:CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)", part, re.IGNORECASE)
        if pk_m:
            pk_cols = [strip_quotes(c).strip() for c in pk_m.group(1).split(",")]
            continue
        fk_m = re.match(
            r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\(\"?(\w+)\"?\)\s+REFERENCES\s+\"?(\w+)\"?\s*(?:\(\"?(\w+)\"?\))?",
            part, re.IGNORECASE)
        if fk_m:
            table.inline_fks.append((fk_m.group(1), fk_m.group(2), fk_m.group(3) or "id"))
            continue

    for part in parts:
        upper = part.upper().lstrip()
        if re.match(r"(PRIMARY\s+KEY|UNIQUE\s*\(|CHECK\s*\(|CONSTRAINT\s+\w+\s+(PRIMARY|UNIQUE|CHECK|FOREIGN)|FOREIGN\s+KEY)", upper):
            continue
        col = parse_column(part, table_name)
        if col:
            table.columns.append(col)

    for col in table.columns:
        if col.name in pk_cols:
            col.is_pk = True

    return table


def parse_alter_fks(stmts: list[str]) -> list[AlterFk]:
    fks = []
    for stmt in stmts:
        m = re.match(
            r"ALTER\s+TABLE\s+\"?(\w+)\"?\s+ADD\s+CONSTRAINT\s+\S+\s+FOREIGN\s+KEY\s*\(\"?(\w+)\"?\)\s+REFERENCES\s+\"?(\w+)\"?\s*(?:\(\"?(\w+)\"?\))?",
            stmt, re.IGNORECASE | re.DOTALL)
        if m:
            fks.append(AlterFk(m.group(1), m.group(2), m.group(3), m.group(4) or "id"))
    return fks


# ---------------------------------------------------------------------------
# d.json field builders
# ---------------------------------------------------------------------------

def build_id_field(col: ColumnInfo, sql_table: str, prefix: Optional[str],
                   use_default_id: bool, override_table_name: Optional[str] = None) -> dict:
    if use_default_id:
        return {
            "name": col.name,
            "type": "Integer",
            "comment": "Identifier",
            "modifiers": ["PERSISTENT", "ID", "GENERATED"],
            "entity": {"cascadeTypes": []}
        }
    base = override_table_name if override_table_name else sql_table
    effective = f"{prefix.lower()}_{base}" if prefix else base
    s = seq_name(effective)
    return {
        "name": col.name,
        "type": "Integer",
        "comment": "Identifier",
        "modifiers": ["PERSISTENT", "ID"],
        "annotations": [
            f"@javax.persistence.SequenceGenerator(name=\"{s}\",sequenceName=\"{s}\",allocationSize=1)",
            f"@javax.persistence.GeneratedValue(strategy=javax.persistence.GenerationType.SEQUENCE, generator=\"{s}\")"
        ],
        "entity": {"cascadeTypes": ["PERSIST", "MERGE"], "orphanRemoval": False}
    }


def build_regular_field(col: ColumnInfo, tbl_name: str) -> dict:
    modifiers = ["PERSISTENT"]
    if col.is_unique:
        modifiers.append("UNIQUE")
    return {
        "name": col.name,
        "type": map_sql_type(col.sql_type, tbl_name, col.name),
        "modifiers": modifiers,
        "entity": {"cascadeTypes": ["PERSIST", "MERGE"], "orphanRemoval": False}
    }


def build_many_to_one_field(fname: str, ref_table: str, namespace: str, prefix: Optional[str]) -> dict:
    return {
        "name": fname,
        "type": assoc_type(namespace, ref_table, prefix),
        "modifiers": ["PERSISTENT"],
        "entity": {"association": "MANY_TO_ONE", "cascadeTypes": ["PERSIST", "MERGE"], "orphanRemoval": False}
    }


def build_one_to_many_field(fname: str, ref_table: str, mapped_by: str, namespace: str, prefix: Optional[str]) -> dict:
    return {
        "name": fname,
        "type": f"java.util.Set<{assoc_type(namespace, ref_table, prefix)}>",
        "modifiers": ["PERSISTENT"],
        "entity": {"association": "ONE_TO_MANY", "cascadeTypes": ["PERSIST", "MERGE"],
                   "mappedByFieldName": mapped_by, "orphanRemoval": False}
    }


# ---------------------------------------------------------------------------
# d.json document builder
# ---------------------------------------------------------------------------

def build_djson(
    table: TableInfo,
    namespace: str,
    prefix: Optional[str],
    use_default_id: bool,
    one_to_many_additions: list[tuple[str, str, str]],
    fk_cols: set[str],
    many_to_one_fields: list[tuple[str, str, str]],
    single_mode: bool = False,
    override_table_name: Optional[str] = None,
) -> dict:
    fields = []

    pk_col = next((c for c in table.columns if c.is_pk), None)
    if pk_col:
        fields.append(build_id_field(pk_col, table.name, prefix, use_default_id, override_table_name))

    for col in table.columns:
        if col.is_pk or col.name in fk_cols:
            continue
        fields.append(build_regular_field(col, table.name))

    for (fname, ref_table, _) in many_to_one_fields:
        fields.append(build_many_to_one_field(fname, ref_table, namespace, prefix))

    for (fname, owning_table, mapped_by) in one_to_many_additions:
        fields.append(build_one_to_many_field(fname, owning_table, mapped_by, namespace, prefix))

    # entity block
    if single_mode:
        tname = build_table_name(table.name, prefix, override_table_name)
    else:
        tname = f"{prefix.lower()}_{table.name}" if prefix else table.name

    entity_block = {}
    if tname:
        entity_block["tableName"] = tname

    return {
        "$schema": "https://json-schema.axonivy.com/data-class/12.0.0/data-class.json",
        "simpleName": simple_name(table.name, prefix),
        "namespace": namespace,
        "fields": fields,
        "entity": entity_block,
    }


# ---------------------------------------------------------------------------
# Association resolver
# ---------------------------------------------------------------------------

def resolve_associations(tables: dict[str, TableInfo], alter_fks: list[AlterFk],
                         namespace: str, prefix: Optional[str]) -> dict[str, dict]:
    result: dict[str, dict] = {t: {"fk_cols": set(), "many_to_one": [], "one_to_many": []} for t in tables}

    def get_pks(tname: str) -> set[str]:
        return {c.name for c in tables[tname].columns if c.is_pk} if tname in tables else set()

    def register(owning: str, fk_col: str, ref: str, mapped_by_hint: Optional[str] = None):
        if owning not in result:
            result[owning] = {"fk_cols": set(), "many_to_one": [], "one_to_many": []}
        if ref not in result:
            result[ref] = {"fk_cols": set(), "many_to_one": [], "one_to_many": []}

        fname = to_camel(fk_col[:-3] if fk_col.lower().endswith("_id") else fk_col)
        result[owning]["fk_cols"].add(fk_col)
        result[owning]["many_to_one"].append((fname, ref, fk_col))

        back = pluralize_camel(to_camel(owning))
        result[ref]["one_to_many"].append((back, owning, mapped_by_hint or fname))

    for tname, table in tables.items():
        for (fk_col, ref_table, _) in table.inline_fks:
            register(tname, fk_col, ref_table)

    for fk in alter_fks:
        src_is_pk = fk.src_col in get_pks(fk.src_table)
        ref_is_pk = fk.ref_col in get_pks(fk.ref_table)

        if src_is_pk and not ref_is_pk:
            register(fk.ref_table, fk.ref_col, fk.src_table)
        else:
            register(fk.src_table, fk.src_col, fk.ref_table)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Axon Ivy d.json dataclass files from SQL DDL.")
    parser.add_argument("input", help="Input SQL file")
    parser.add_argument("--namespace", required=True, help="Java namespace, e.g. com.example.entities")
    parser.add_argument("--prefix", default=None, help="Optional class/table prefix, e.g. History")
    parser.add_argument("--output", default=".", help="Output directory (default: current dir)")
    parser.add_argument("--useDefaultId", action="store_true",
                        help="Emit GENERATED modifier on id instead of SequenceGenerator annotations")
    parser.add_argument("--single", action="store_true",
                        help="Single mode: SQL must contain exactly one CREATE TABLE")
    parser.add_argument("--tableName", default=None,
                        help="(Single mode only) Override entity tableName. Combined with --prefix if given.")
    args = parser.parse_args()

    if args.tableName and not args.single:
        parser.error("--tableName can only be used with --single")

    sql_path = Path(args.input)
    if not sql_path.exists():
        print(f"ERROR: File not found: {sql_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    stmts = split_statements(normalize_sql(sql_path.read_text(encoding="utf-8")))

    tables: dict[str, TableInfo] = {}
    for stmt in stmts:
        t = parse_create_table(stmt)
        if t:
            tables[t.name] = t

    if args.single and len(tables) != 1:
        print(f"ERROR: --single requires exactly one CREATE TABLE, found {len(tables)}", file=sys.stderr)
        sys.exit(1)

    alter_fks = parse_alter_fks(stmts)
    assoc = resolve_associations(tables, alter_fks, args.namespace, args.prefix)

    for tname, table in tables.items():
        info = assoc.get(tname, {"fk_cols": set(), "many_to_one": [], "one_to_many": []})
        djson = build_djson(
            table=table,
            namespace=args.namespace,
            prefix=args.prefix,
            use_default_id=args.useDefaultId,
            one_to_many_additions=info["one_to_many"],
            fk_cols=info["fk_cols"],
            many_to_one_fields=info["many_to_one"],
            single_mode=args.single,
            override_table_name=args.tableName if args.single else None,
        )
        out_file = out_dir / f"{simple_name(tname, args.prefix)}.d.json"
        out_file.write_text(json.dumps(djson, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Written: {out_file}")

    if UNKNOWN_TYPE_WARNINGS:
        log_file = out_dir / "warnings.log"
        with log_file.open("w", encoding="utf-8") as f:
            f.write("Unknown SQL types — mapped to String as fallback:\n\n")
            f.write(f"{'Table':<30} {'Column':<30} {'SQL Type'}\n")
            f.write("-" * 70 + "\n")
            for (tbl, col, sql_type) in UNKNOWN_TYPE_WARNINGS:
                f.write(f"{tbl:<30} {col:<30} {sql_type}\n")
        print(f"\n  Warnings written: {log_file}")
    else:
        print("\n  No type warnings.")


if __name__ == "__main__":
    main()
