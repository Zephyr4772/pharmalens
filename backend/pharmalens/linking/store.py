"""Derived links between records and entities, kept apart from the source tables.

Every link carries how it was made (method), how sure we are (confidence 0-1), the evidence a person can check,
and the licence class of the data it was derived from (the strictest of its inputs, from licensing.py), so a later
decision about what can go public applies to links too.

Each linker owns its rows (column `linker`): re-running a linker replaces only its own links, and dropping them
(DELETE ... WHERE linker = ?) reverts it without touching anything else. Source tables are never modified.
"""
from datetime import datetime

import pandas as pd

from .. import db, licensing

HIGH = 0.85          # shown in the UI by default; anything below is "inferred" and labelled as such

DDL = """
CREATE TABLE IF NOT EXISTS entity_links (
    linker      VARCHAR,     -- which linker made it (one per roadmap item / source)
    src_table   VARCHAR,     -- the record's table
    src_key     VARCHAR,     -- the record's key in that table (id, natural key or dedupe key)
    dst_type    VARCHAR,     -- molecule | combo | product | company | parent | us_application | ...
    dst_id      VARCHAR,
    method      VARCHAR,     -- how it was resolved (see each linker)
    confidence  DOUBLE,
    evidence    VARCHAR,     -- the text or keys that matched, for spot checks
    licence     VARCHAR,     -- licensing class of the inputs (strictest wins)
    created_at  TIMESTAMP,
    PRIMARY KEY (linker, src_table, src_key, dst_type, dst_id)
);
CREATE TABLE IF NOT EXISTS event_entities (   -- every entity an event is about (events.entity_* holds only one)
    event_id    BIGINT,
    entity_type VARCHAR,
    entity_id   VARCHAR,
    method      VARCHAR,
    confidence  DOUBLE,
    evidence    VARCHAR,
    licence     VARCHAR,
    PRIMARY KEY (event_id, entity_type, entity_id)
);
CREATE TABLE IF NOT EXISTS price_unit_obs (    -- price observations with the pack they refer to, per unit
    product_id  INTEGER,
    observed_on DATE,
    source      VARCHAR,
    mrp         DOUBLE,
    pack_text   VARCHAR,
    pack_qty    DOUBLE,
    pack_basis  VARCHAR,     -- where the pack came from: source_row | mfr_list | product_pack (assumed)
    unit_price  DOUBLE,
    comparable  BOOLEAN,     -- safe to put on one per-unit trend line with the product's other comparable points
    method      VARCHAR,
    confidence  DOUBLE,
    note        VARCHAR,
    licence     VARCHAR,
    PRIMARY KEY (product_id, observed_on, source)
);
CREATE TABLE IF NOT EXISTS linker_runs (
    linker VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP, links INTEGER, high INTEGER, note VARCHAR
);
"""


def ensure() -> None:
    with db.writer() as w:
        w.execute(DDL)


def licence_of(*tables: str) -> str:
    """Strictest licence class among the inputs (derived work of ours is 'open' on its own)."""
    classes = [licensing.table_class(t) for t in tables] + [licensing.OPEN]
    return max(classes, key=licensing.RANK.__getitem__)


def replace(linker: str, rows: list[dict], note: str = "") -> dict:
    """Swap this linker's links for `rows` (dicts with the entity_links columns except linker / created_at)."""
    ensure()
    started = datetime.now()
    cols = ["linker", "src_table", "src_key", "dst_type", "dst_id", "method", "confidence", "evidence", "licence", "created_at"]
    df = pd.DataFrame([{**r, "linker": linker, "created_at": started, "src_key": str(r["src_key"]), "dst_id": str(r["dst_id"])}
                       for r in rows], columns=cols)
    df = df.drop_duplicates(subset=["src_table", "src_key", "dst_type", "dst_id"], keep="first")
    with db.writer() as w:
        w.execute("DELETE FROM entity_links WHERE linker = ?", [linker])
        if len(df):
            w.register("_l", df)
            w.execute(f"INSERT INTO entity_links SELECT {', '.join(cols)} FROM _l")
            w.unregister("_l")
        high = int((df["confidence"] >= HIGH).sum()) if len(df) else 0
        w.execute("INSERT INTO linker_runs VALUES (?, ?, ?, ?, ?, ?)", [linker, started, datetime.now(), len(df), high, note])
    return {"linker": linker, "links": len(df), "high": high}
