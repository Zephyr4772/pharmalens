"""Write a spot-check sample of derived links to docs/link-samples/<item>.md.

    py -3 analysis/samples.py <db> <item> <linker-prefix|event_entities|price_unit_obs> [n]

Samples only links that are new (not already present in the source table's own columns) where that can be told,
and shows each link's method, confidence, licence and the evidence it was made from.
"""
import sys

import duckdb

NAMES = {"molecule": "SELECT name FROM molecules WHERE id = CAST(? AS INTEGER)",
         "combo": "SELECT label FROM combos WHERE id = CAST(? AS INTEGER)",
         "company": "SELECT name FROM companies WHERE id = CAST(? AS INTEGER)",
         "parent": "SELECT name FROM parents WHERE id = CAST(? AS INTEGER)",
         "product": "SELECT name FROM products WHERE id = CAST(? AS INTEGER)"}


def name(c, t, i):
    q = NAMES.get(t)
    if not q:
        return i
    try:
        r = c.execute(q, [i]).fetchone()
        return r[0] if r else i
    except duckdb.Error:
        return i


def main(db, item, what, n=50):
    c = duckdb.connect(db, read_only=True)
    lines = [f"# Link sample: {item}", "", f"{n} random new links from `{what}` in `{db.split('/')[-1]}`, for spot checks. "
             "High = confidence ≥ 0.85 (shown by default); lower values are labelled inferred in the UI.", ""]
    if what == "event_entities":
        rows = c.execute(f"""SELECT x.event_id, e.kind, e.title, x.entity_type, x.entity_id, x.method, x.confidence, x.evidence, x.licence
                             FROM event_entities x JOIN events e ON e.id = x.event_id
                             WHERE NOT (e.entity_type IS NOT DISTINCT FROM x.entity_type AND CAST(e.entity_id AS VARCHAR) IS NOT DISTINCT FROM x.entity_id)
                             ORDER BY random() LIMIT {n}""").fetchall()
        lines += ["| event | kind | title | → entity | method | conf | licence | evidence |", "|---|---|---|---|---|---|---|---|"]
        for eid, k, t, et, ei, m, cf, ev, lic in rows:
            lines.append(f"| {eid} | {k} | {(t or '')[:70]} | {et}: {name(c, et, ei)} | {m} | {cf:.2f} | {lic} | {(ev or '')[:120]} |")
    elif what == "price_unit_obs":
        rows = c.execute(f"""WITH p AS (SELECT product_id FROM price_unit_obs GROUP BY 1 HAVING count(*) >= 2 ORDER BY random() LIMIT {n // 2})
                             SELECT u.product_id, pr.name, u.source, u.observed_on, u.mrp, u.pack_text, u.pack_qty, u.pack_basis, u.unit_price,
                                    u.comparable, u.method, u.confidence, u.note, u.licence
                             FROM price_unit_obs u JOIN p USING (product_id) JOIN products pr ON pr.id = u.product_id
                             ORDER BY u.product_id, u.observed_on""").fetchall()
        lines += ["| product | source | date | MRP | pack | qty | basis | ₹/unit | comparable | method | conf | note |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for pid, pn, src, d, mrp, pt, pq, pb, up, cmp_, m, cf, note, lic in rows:
            lines.append(f"| {pid} {pn[:40]} | {src} | {d} | {mrp} | {(pt or '')[:30]} | {pq} | {pb} | {up if up is None else round(up, 3)} | {cmp_} | {m} | {cf:.2f} | {(note or '')[:80]} |")
    else:
        prefixes = what.split(",")          # several linkers: n is split evenly between them
        rows = []
        for pf in prefixes:
            rows += c.execute(f"""SELECT linker, src_table, src_key, dst_type, dst_id, method, confidence, licence, evidence FROM entity_links
                                  WHERE linker LIKE ? ORDER BY random() LIMIT {max(1, n // len(prefixes))}""", [pf + "%"]).fetchall()
        lines += ["| record | → entity | method | conf | licence | evidence |", "|---|---|---|---|---|---|"]
        for lk, st, sk, dt, di, m, cf, lic, ev in rows:
            lines.append(f"| {st}: `{sk[:50]}` | {dt}: {name(c, dt, di)} | {m} | {cf:.2f} | {lic} | {(ev or '').replace('|', '/')[:160]} |")
    out = f"docs/link-samples/{item}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(out, len(rows))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else 50)
