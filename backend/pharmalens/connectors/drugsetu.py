"""DrugSetu: retired source, kept as stored data.

The DrugSetu developer API (api.drugsetu.com) was used during its 7-day trial in October 2026 and then retired: a
new account would also stop after ~500 queries, and our own sources replace what it gave (label text shared by
composition, NPPA launch prices, new-brand tracking from the CDSCO registry and CDCI, manufacturers' Form V price
lists). Everything it returned is kept: `drugsetu_products` (456 products, merged into the catalog by build_core)
and the raw records in data/sources/drugsetu/*.jsonl.gz. Nothing here calls the API.
"""
from .. import db


def saved_record(product_id: int) -> dict | None:
    """The stored DrugSetu record for a catalog product, matched by id or exact normalised name."""
    cur = db.cursor()
    p = db.one(cur, "SELECT name_norm FROM products WHERE id = ?", [product_id])
    if not p:
        return None
    try:
        row = db.one(cur, """SELECT * FROM drugsetu_products WHERE catalog_product_id = ? OR name_norm = ?
                             ORDER BY fetched_at DESC LIMIT 1""", [product_id, p["name_norm"]])
    except Exception:  # noqa: BLE001 — a database built without the stored table simply has no record
        return None
    return {**row, "stale": True} if row else None
