"""CLI: py -3 -m pharmalens.connectors {list | run <name>|all}

If the API server is running it owns the database, so the run is delegated to it
over HTTP; otherwise the connector runs in this process.
"""
import json
import sys

import httpx

from . import REGISTRY

SERVER = "http://127.0.0.1:8010/api/v1/admin/connectors"


def main(argv: list[str]):
    if not argv or argv[0] == "list":
        for n, c in REGISTRY.items():
            print(f"{n:20s} {c.schedule}  {c.title}")
        return
    if argv[0] != "run" or len(argv) < 2:
        print(__doc__)
        return
    names = list(REGISTRY) if argv[1] == "all" else argv[1:]
    for n in names:
        if n not in REGISTRY:
            print(f"unknown connector {n}")
            continue
        try:
            r = httpx.post(f"{SERVER}/{n}/run", timeout=3600)
            print(json.dumps(r.json()))
            continue
        except httpx.ConnectError:
            pass
        from ..scheduler import run_now
        print(json.dumps(run_now(n), default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
