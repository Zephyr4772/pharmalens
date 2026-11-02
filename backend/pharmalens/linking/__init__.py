"""Derived links (Phase 1 of docs/data-depth-audit.md). Each module is one roadmap item; `run(names)` runs them.

    py -3 -m pharmalens.linking [item ...]      # items: molecules global events prices bans launches companies
"""
import importlib
import logging

log = logging.getLogger("pharmalens.linking")

ITEMS = ["hygiene", "molecules", "global_status", "events", "prices", "bans", "launches", "companies", "makers"]       # grows as Phase 1 items land (each its own commit)


def run(names: list[str] | None = None) -> list[dict]:
    from .store import ensure
    ensure()
    out = []
    for name in names or ITEMS:
        mod = importlib.import_module(f".{name}", __name__)
        res = mod.run()
        out += res if isinstance(res, list) else [res]
        log.info("linker %s: %s", name, res)
    return out
