"""Derived links (Phase 1 of docs/data-depth-audit.md). Each module is one roadmap item; `run(names)` runs them.

    py -3 -m pharmalens.linking [item ...]      # items: molecules global events prices bans launches companies
"""
import importlib
import logging
import os

log = logging.getLogger("pharmalens.linking")

ITEMS = ["hygiene", "molecules", "global_status", "events", "prices", "bans", "launches", "companies", "makers", "sites", "nsq_products"]       # grows as Phase 1 items land (each its own commit)


BURST = os.getenv("PHARMALENS_DUCKDB_BURST", "850MB")   # one retry of an item that ran out of memory


def run(names: list[str] | None = None) -> list[dict]:
    """Run the items in order. Each item replaces only its own links in one transaction, so an item that fails is
    rolled back and retried once after a checkpoint, with a higher memory limit when memory was the cause; an item
    that still fails is reported and the rest still run."""
    import duckdb

    from .. import db
    from .store import ensure
    ensure()
    out = []
    for name in names or ITEMS:
        mod = importlib.import_module(f".{name}", __name__)
        try:
            res = mod.run()
        except duckdb.OutOfMemoryException:
            log.warning("linker %s out of memory (%s); retrying at %s", name, db.memory_top(), BURST)
            with db.WRITE_LOCK:
                db.cursor().execute("CHECKPOINT")
            try:
                with db.memory_limit(BURST):
                    res = mod.run()
            except Exception as e:  # noqa: BLE001 — one item must not stop the others
                log.exception("linker %s failed", name)
                res = {"linker": name, "error": f"{type(e).__name__}: {str(e)[:200]} [{db.memory_top()}]"}
        except Exception as e:  # noqa: BLE001
            log.exception("linker %s failed", name)
            res = {"linker": name, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        out += res if isinstance(res, list) else [res]
        log.info("linker %s: %s", name, res)
    return out
