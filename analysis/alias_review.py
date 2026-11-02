"""Export molecule alias candidates for review: docs/molecule-aliases-review.csv.

    py -3 analysis/alias_review.py <db>

Pending rows (applied = false) are what the rules would not apply on their own; applied rows are listed too so any of
them can be vetoed. To decide, copy a row's alias_id and canonical_id into backend/pharmalens/seed/molecule_aliases.csv
with decision accept or reject; the next linker run honours it.
"""
import csv
import sys

import duckdb


def main(db: str) -> None:
    c = duckdb.connect(db, read_only=True)
    rows = c.execute("""SELECT x.applied, x.method, x.confidence, a.id, a.name, a.product_count, k.id, k.name, k.product_count, x.evidence
                        FROM molecule_aliases x JOIN molecules a ON a.id = x.alias_id JOIN molecules k ON k.id = x.canonical_id
                        ORDER BY x.applied, x.method, a.product_count DESC""").fetchall()
    out = "docs/molecule-aliases-review.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["applied", "method", "confidence", "alias_id", "alias_name", "alias_products", "canonical_id", "canonical_name",
                    "canonical_products", "evidence", "decision"])
        for r in rows:
            w.writerow(list(r) + [""])
    print(out, len(rows), "rows,", sum(1 for r in rows if not r[0]), "pending")


if __name__ == "__main__":
    main(sys.argv[1])
