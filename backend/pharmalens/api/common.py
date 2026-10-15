import csv
import io
import math
from datetime import date, datetime
from decimal import Decimal

from fastapi.responses import StreamingResponse


def clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, Decimal):
        return float(v)
    return v


def cleanrows(rows: list[dict]) -> list[dict]:
    return [{k: clean(v) for k, v in r.items()} for r in rows]


def paged(total: int, page: int, limit: int, data: list[dict], **extra) -> dict:
    return {"meta": {"total": total, "page": page, "limit": limit, "pages": max(1, math.ceil(total / limit))},
            "data": cleanrows(data), **extra}


def csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in r.items()})
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})


def ids(s: str | None) -> list[int]:
    return [int(x) for x in (s or "").split(",") if x.strip().isdigit()]


SORTS = {
    "mrp_asc": "p.mrp ASC NULLS LAST", "mrp_desc": "p.mrp DESC NULLS LAST",
    "unit_asc": "p.unit_price ASC NULLS LAST", "unit_desc": "p.unit_price DESC NULLS LAST",
    "name": "p.name", "reach": "p.source_count DESC, p.mrp DESC NULLS LAST",
}
