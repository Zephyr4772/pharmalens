"""Clinical label text from the master dataset (1mg-derived columns) into `product_info`.

    cd backend && py -3 -m pharmalens.pipeline.product_info

Fields: introduction, benefits, how to use, how it works, quick tips, detailed side effects,
and a structured safety profile (alcohol / pregnancy / breastfeeding / driving / kidney / liver)
graded unsafe · consult · caution · safe-if-prescribed · safe. Rows are keyed by catalog product id via
products.src_id, so this runs against an existing build (also called at the end of build_core).
Stop the API server first (DuckDB single writer).
"""
import json
import re
import time

import duckdb
import pandas as pd

from ..config import DB_PATH, MASTER_DIR

TABLE_SQL = """
CREATE OR REPLACE TABLE product_info (
    product_id     INTEGER PRIMARY KEY,
    introduction   VARCHAR,
    benefits       JSON,      -- [{"title": ..., "text": ...}]
    how_to_use     VARCHAR,
    how_it_works   VARCHAR,
    quick_tips     JSON,      -- ["...", ...]
    side_effects   JSON,      -- ["Headache", ...]
    safety         JSON,      -- {"alcohol": {"level": "caution", "text": "..."}, ...}
    source         VARCHAR
)"""

SAFETY_KEYS = {"alcohol": "alcohol", "pregnancy": "pregnancy", "breast feeding": "breastfeeding", "breastfeeding": "breastfeeding",
               "driving": "driving", "kidney": "kidney", "liver": "liver"}
LEVELS = [  # order matters: the label's verdict wording outranks the boilerplate "please consult your doctor"
    ("unsafe", r"\bunsafe\b|do not drive|should not|must not|is not safe|not recommended|strictly prohibited|contraindicated"),
    ("caution", r"caution|use with care|dose adjustment (may be|is|might be) (needed|required)|may (cause|make|affect|reduce|impair|decrease)|"
                r"regular monitoring|should be used with care"),
    ("safe_if_prescribed", r"safe if prescribed|probably safe|generally (considered )?safe|appears to be safe"),
    # unknowns before plain "safe": "it is not known whether it is safe" must never read as safe
    ("consult", r"not known|unknown|no (data|information)|limited (data|information|studies)|not been studied"),
    ("safe", r"\bsafe\b|no interaction|does not (usually )?affect|nodoseadj|not cause any harmful|no harmful"),
    ("not_applicable", r"not relevant|intended for use in hospitali[sz]ed"),
    ("consult", r"consult your doctor|please consult"),
]


def lines(s: str | None) -> list[str]:
    if not s or not isinstance(s, str):
        return []
    return [re.sub(r"\s+", " ", x).strip(" ,•-") for x in s.split("\n") if x.strip(" ,•-\t")]


def level_of(text: str) -> str:
    t = re.sub(r"no dose adjustment", "nodoseadj", text.lower())
    for lvl, rx in LEVELS:
        if re.search(rx, t):
            return lvl
    return "info"


def parse_safety(raw: str | None, explicit: dict[str, str | None]) -> dict:
    out = {}
    parts = lines(raw)
    i = 0
    while i < len(parts):
        key = SAFETY_KEYS.get(parts[i].lower())
        if key and i + 1 < len(parts):
            txt = parts[i + 1]
            out[key] = {"level": level_of(txt), "text": txt}
            i += 2
        else:
            i += 1
    for key, txt in explicit.items():
        if txt and isinstance(txt, str) and key not in out:
            out[key] = {"level": level_of(txt), "text": txt.strip()}
    return out


def parse_benefits(raw: str | None) -> list[dict]:
    """'Treatment of X' heading lines followed by a paragraph."""
    out, cur = [], None
    for ln in lines(raw):
        if len(ln) < 90 and not ln.endswith("."):
            cur = {"title": ln, "text": ""}
            out.append(cur)
        elif cur is not None:
            cur["text"] = (cur["text"] + " " + ln).strip()
        else:
            out.append({"title": "", "text": ln})
    return out


def parse_side_effects(raw: str | None) -> list[str]:
    items = [x for x in lines(raw) if len(x) < 80 and not x.lower().startswith(("common side effects", "most side effects"))]
    return list(dict.fromkeys(items))[:60]


def build(con: duckdb.DuckDBPyConnection | None = None) -> int:
    t0 = time.time()
    own = con is None
    con = con or duckdb.connect(str(DB_PATH))
    P = str(MASTER_DIR / "medicines_full.parquet").replace("\\", "/")
    src = con.execute(f"""
        SELECT p.id, m.introduction, m.benefits, m.how_to_use, m.how_it_works, m.quick_tips, m.side_effects_detail,
               m.safety_advice, m.alcohol_warning, m.pregnancy_warning, m.breastfeeding_warning,
               m.driving_advice, m.kidney_advice, m.liver_advice
        FROM '{P}' m JOIN products p ON p.src_id = m.medicine_id
        WHERE coalesce(m.introduction, m.benefits, m.how_to_use, m.how_it_works, m.quick_tips, m.safety_advice,
                       m.alcohol_warning, m.pregnancy_warning) IS NOT NULL""").fetchall()
    rows = []
    for (pid, intro, ben, use, how, tips, se, sa, alc, preg, bf, drv, kid, liv) in src:
        safety = parse_safety(sa, {"alcohol": alc, "pregnancy": preg, "breastfeeding": bf, "driving": drv, "kidney": kid, "liver": liv})
        rows.append((pid, re.sub(r"\s+", " ", intro).strip() if intro else None,
                     json.dumps(parse_benefits(ben), ensure_ascii=False) if ben else None,
                     re.sub(r"\s+", " ", use).strip() if use else None,
                     re.sub(r"\s+", " ", how).strip() if how else None,
                     json.dumps(lines(tips), ensure_ascii=False) if tips else None,
                     json.dumps(parse_side_effects(se), ensure_ascii=False) if se else None,
                     json.dumps(safety, ensure_ascii=False) if safety else None,
                     "Indian Medicine Master Dataset (1mg-derived label text)"))
    con.execute(TABLE_SQL)
    df = pd.DataFrame(rows, columns=["product_id", "introduction", "benefits", "how_to_use", "how_it_works", "quick_tips",
                                     "side_effects", "safety", "source"])
    con.register("_pi", df)
    con.execute("INSERT INTO product_info SELECT * FROM _pi")
    con.unregister("_pi")
    if own:
        con.execute("CHECKPOINT")
        con.close()
    print(f"product_info: {len(rows):,} products in {time.time() - t0:.0f}s")
    return len(rows)


if __name__ == "__main__":
    build()
