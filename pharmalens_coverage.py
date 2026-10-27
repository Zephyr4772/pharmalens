#!/usr/bin/env python3
"""
Read-only PharmaLens DuckDB coverage report generator.

Usage from the PharmaLens project root:
    py -3 tools\pharmalens_coverage.py
Or provide an explicit database path:
    py -3 tools\pharmalens_coverage.py "D:\pharmacopy\pharmalens\data\pharmalens.duckdb"

The script opens DuckDB in read-only mode and writes PHARMALENS_COVERAGE.md
in the current working directory (or to --output). It does not inspect row
contents, secrets, or personal data; it reports schema metadata and counts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print(
        "Could not import duckdb. Activate the project's environment or install "
        "the dependency from the project's existing requirements file.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def qi(identifier: str) -> str:
    """Quote a DuckDB identifier safely."""
    return '"' + identifier.replace('"', '""') + '"'


def md_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def fmt_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.2f} {unit}"
        value /= 1024
    return f"{value:,.2f} TB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a read-only PharmaLens DuckDB coverage report.")
    parser.add_argument(
        "database",
        nargs="?",
        default=os.environ.get("PHARMALENS_DB", r"data\pharmalens.duckdb"),
        help=r"Path to DuckDB file (default: data\pharmalens.duckdb, relative to current directory).",
    )
    parser.add_argument(
        "--output",
        default="PHARMALENS_COVERAGE.md",
        help="Markdown report path (default: PHARMALENS_COVERAGE.md).",
    )
    parser.add_argument(
        "--skip-counts",
        action="store_true",
        help="Only report schemas/columns; skip potentially expensive exact row counts.",
    )
    args = parser.parse_args()

    db_path = Path(args.database).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        print("Pass the full path to pharmalens.duckdb if it is outside the project root.", file=sys.stderr)
        return 2

    stat = db_path.stat()
    generated = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    lines: list[str] = [
        "# PharmaLens Database Coverage",
        "",
        f"- **Generated:** {generated}",
        f"- **Database:** `{db_path}`",
        f"- **File size:** {fmt_bytes(stat.st_size)} ({stat.st_size:,} bytes)",
        "- **Inspection mode:** DuckDB opened read-only; no table contents or sample records exported.",
        "",
        "> Exact row counts may take time on large tables or views. A failed count is recorded as an error rather than guessed.",
        "",
        "## Summary",
        "",
    ]

    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        print(f"Could not open database in read-only mode: {exc}", file=sys.stderr)
        print("If the app currently has the database open for writing, stop its backend and retry.", file=sys.stderr)
        return 3

    try:
        table_rows = con.execute(
            """
            SELECT table_catalog, table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_catalog, table_schema, table_name
            """
        ).fetchall()

        lines.extend([
            f"- **Tables/views discovered:** {len(table_rows)}",
            f"- **Exact counts requested:** {'No' if args.skip_counts else 'Yes'}",
            "",
            "## Table inventory",
            "",
            "| Catalog | Schema | Object | Type | Exact rows |",
            "|---|---|---|---|---:|",
        ])

        inventory = []
        for catalog, schema, table, obj_type in table_rows:
            row_count = "Skipped"
            if not args.skip_counts:
                try:
                    # Identifiers come from DuckDB's own metadata and are quoted.
                    row_count = f"{con.execute(f'SELECT COUNT(*) FROM {qi(schema)}.{qi(table)}').fetchone()[0]:,}"
                except Exception as exc:
                    row_count = f"ERROR: {str(exc)[:120]}"
            inventory.append((catalog, schema, table, obj_type, row_count))
            lines.append("| " + " | ".join(md_cell(x) for x in (catalog, schema, table, obj_type, row_count)) + " |")

        lines.extend(["", "## Column-level schema", ""])
        for catalog, schema, table, obj_type, _ in inventory:
            lines.extend([
                f"### `{schema}.{table}`",
                "",
                f"- **Object type:** {obj_type}",
            ])
            if not args.skip_counts:
                lines.append(f"- **Exact rows:** {_row_count_for_display(inventory, schema, table)}")
            lines.extend([
                "",
                "| Ordinal | Column | Data type | Nullable | Default |",
                "|---:|---|---|---|---|",
            ])
            try:
                cols = con.execute(
                    """
                    SELECT ordinal_position, column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = ? AND table_name = ?
                    ORDER BY ordinal_position
                    """,
                    [schema, table],
                ).fetchall()
                for ordinal, col, data_type, nullable, default in cols:
                    lines.append("| " + " | ".join(md_cell(x) for x in (ordinal, col, data_type, nullable, default)) + " |")
            except Exception as exc:
                lines.append(f"| | Schema query failed: {md_cell(str(exc)[:150])} | | | |")
            lines.append("")

        # Inspect temporal typed columns only. Do not scan arbitrary text columns
        # or expose values; only minimum and maximum are reported.
        temporal_candidates = []
        for catalog, schema, table, obj_type, _ in inventory:
            try:
                cols = con.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = ? AND table_name = ?
                    ORDER BY ordinal_position
                    """,
                    [schema, table],
                ).fetchall()
            except Exception:
                continue
            for col, data_type in cols:
                typ = data_type.upper()
                name = col.lower()
                is_temporal_type = any(x in typ for x in ("DATE", "TIMESTAMP", "TIME"))
                likely_date_name = any(x in name for x in (
                    "date", "time", "year", "published", "created", "updated",
                    "modified", "filing", "effective", "event", "session"
                ))
                if is_temporal_type and likely_date_name:
                    temporal_candidates.append((schema, table, col, data_type, obj_type))

        lines.extend([
            "## Temporal coverage (typed date/time columns)",
            "",
            "Only columns typed as DATE/TIME/TIMESTAMP and with date-like names are checked. The report contains extrema only, not individual records.",
            "",
            "| Schema | Object | Column | Type | Minimum | Maximum |",
            "|---|---|---|---|---|---|",
        ])
        if temporal_candidates:
            for schema, table, col, data_type, obj_type in temporal_candidates:
                try:
                    result = con.execute(
                        f"SELECT MIN({qi(col)}), MAX({qi(col)}) FROM {qi(schema)}.{qi(table)}"
                    ).fetchone()
                    lo, hi = result
                    lines.append("| " + " | ".join(md_cell(x) for x in (
                        schema, table, col, data_type, lo, hi
                    )) + " |")
                except Exception as exc:
                    lines.append("| " + " | ".join(md_cell(x) for x in (
                        schema, table, col, data_type, f"ERROR: {str(exc)[:100]}", ""
                    )) + " |")
        else:
            lines.append("| | No matching typed date/time columns found | | | | |")

        lines.extend([
            "",
            "## Notes and limitations",
            "",
            "- Counts are exact when shown as a number; `ERROR` means DuckDB could not complete that count.",
            "- Views may be expensive to count because they can execute their underlying query.",
            "- This report does not inspect data quality, semantic correctness, source freshness, API success, or join completeness.",
            "- Date extrema are reported only for typed date/time columns with date-like names. Dates stored as text are intentionally not parsed automatically.",
            "- No row samples, credentials, API keys, or source record contents are exported.",
            "- Review this report before sharing it publicly; table and column names can reveal implementation details even though no row values are included.",
            "",
        ])

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
    finally:
        con.close()

    print(f"Coverage report written to: {out_path}")
    print(f"Database inspected read-only: {db_path}")
    print("No database rows were changed.")
    return 0


def _row_count_for_display(inventory, schema, table):
    for _, s, t, _, count in inventory:
        if s == schema and t == table:
            return count
    return "Unknown"


if __name__ == "__main__":
    raise SystemExit(main())
