"""Per-source pack sizes for the catalog's two baseline price points (Phase 1 #11).

The catalog keeps one pack per product (the 2022-24 master's if it had one, else the 2025 scrape's), so the two
historic MRPs can refer to different packs. This reads both raw sources again and writes, per product name, the pack
each source quoted its MRP for:

    py -3 -m pharmalens.pipeline.price_packs        # writes data/derived/price_packs.parquet

Run where the raw catalog files live (they are not on the server); copy the parquet to the server's data/derived/.
The entity_linker's price step reads it if present. Licence: internal (derived from the Kaggle catalog sources).
"""
import duckdb
import pandas as pd

from ..config import DATA_DIR, MASTER_DIR
from ..normalize import norm_product, pack_quantity
from .build_core import parse_onemg_2025, to_float

OUT = DATA_DIR / "derived" / "price_packs.parquet"


def main() -> None:
    con = duckdb.connect()
    M = str(MASTER_DIR).replace("\\", "/") + "/"
    master = con.execute(f"""SELECT medicine_name, pack_size, price_inr, manufacturer FROM read_csv_auto('{M}medicines.csv', sample_size=-1)""").fetchall()
    rows = []
    for name, pack, price, _ in master:
        if name and pack:
            q, unit = pack_quantity(pack)
            rows.append({"name_norm": norm_product(name), "source": "catalog-2022-24", "pack_text": pack, "pack_qty": q,
                         "pack_unit": unit, "mrp": to_float(price)})
    known = [r[3] for r in master if r[3]]
    for key, o in parse_onemg_2025(sorted(set(known))).items():
        if o.get("pack"):
            q, unit = pack_quantity(o["pack"])
            rows.append({"name_norm": key, "source": "1mg-2025", "pack_text": o["pack"], "pack_qty": q, "pack_unit": unit, "mrp": o.get("mrp")})
    df = pd.DataFrame(rows).drop_duplicates(["name_norm", "source"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"{OUT}: {len(df):,} rows ({(df.source == 'catalog-2022-24').sum():,} master, {(df.source == '1mg-2025').sum():,} 2025)")


if __name__ == "__main__":
    main()
