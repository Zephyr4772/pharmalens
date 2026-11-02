"""Roadmap #6: US and EU status of each ingredient combination (Orange Book products, patents and exclusivities,
EMA medicines), so product and molecule pages can show them.

Links go through an ingredient-set node (dst_type 'ingredient_set', id = sorted molecule ids): each combination
links to its set, and each Orange Book product and EMA medicine links to its set, so a product reaches a US or EU
record only when the record's ingredient set equals the combination's exactly (method exact_ingredient_set). Records whose ingredient list was only partly resolved to our molecules (fewer
resolved molecules than listed ingredients) are skipped, so "piperaquine; artenimol" can never match a product of
piperaquine alone. Patents and exclusivities attach through their Orange Book product (application + product no.).
"""
import re

from .. import db
from .store import licence_of, replace


_CMAP: dict[int, int] = {}


def _set(ids: str | None) -> str | None:
    """Sorted canonical molecule ids (molecule hygiene folds aliases), as the ingredient-set key."""
    if not ids:
        return None
    return ",".join(sorted({str(_CMAP.get(int(x), int(x))) for x in ids.split(",") if x.strip()}, key=int))


def run() -> list[dict]:
    from .hygiene import canon_map
    _CMAP.clear()
    _CMAP.update(canon_map())
    cur = db.cursor()
    # each combination's molecule set (all products of a combination share it)
    combos: dict[str, list[int]] = {}
    for cid, s in cur.execute("""SELECT p.combo_id, string_agg(DISTINCT CAST(pm.molecule_id AS VARCHAR), ',')
                                 FROM products p JOIN product_molecules pm ON pm.product_id = p.id
                                 WHERE p.combo_id IS NOT NULL GROUP BY p.combo_id""").fetchall():
        combos.setdefault(_set(s), []).append(cid)
    names = dict(cur.execute("SELECT CAST(id AS VARCHAR), name FROM molecules").fetchall())

    def label(s: str) -> str:
        return " + ".join(names.get(i, i) for i in s.split(","))

    lic_c = licence_of("combos", "product_molecules")
    cset = [{"src_table": "combos", "src_key": cid, "dst_type": "ingredient_set", "dst_id": st, "method": "catalog_molecules",
             "confidence": 1.0, "evidence": label(st), "licence": lic_c} for st, cids in combos.items() if st for cid in cids]
    ob, ema = [], []
    lic_ob = licence_of("us_orange_book")
    for appl, prod, ingr, mids in cur.execute("""SELECT application_number, product_number, ingredients, molecule_ids
                                                 FROM us_orange_book WHERE molecule_ids IS NOT NULL""").fetchall():
        st = _set(mids)
        n_listed = len([x for x in re.split(r";", ingr or "") if x.strip()])
        if not st or len(st.split(",")) != n_listed or st not in combos:
            continue                         # an ingredient we could not resolve, or a set no Indian product has
        ob.append({"src_table": "us_orange_book", "src_key": f"{appl}|{prod}", "dst_type": "ingredient_set", "dst_id": st,
                   "method": "exact_ingredient_set", "confidence": 0.95,
                   "evidence": f"Orange Book ingredients '{ingr}' = {{{label(st)}}}", "licence": lic_ob})
    lic_ema = licence_of("ema_medicines")
    for num, nm, subst, mids in cur.execute("""SELECT ema_product_number, name_of_medicine, coalesce(active_substance, international_non_proprietary_name_inn_common_name),
                                                      molecule_ids FROM ema_medicines WHERE category = 'Human' AND molecule_ids IS NOT NULL""").fetchall():
        st = _set(mids)
        n_listed = len([x for x in re.split(r"[;/]|,\s(?=[a-z])", subst or "") if x.strip()])
        if not st or not num or len(st.split(",")) != n_listed or st not in combos:
            continue
        ema.append({"src_table": "ema_medicines", "src_key": num, "dst_type": "ingredient_set", "dst_id": st,
                    "method": "exact_ingredient_set", "confidence": 0.95,
                    "evidence": f"EMA active substance '{subst}' ({nm}) = {{{label(st)}}}", "licence": lic_ema})
    # patents and exclusivities need no link of their own: they belong to an Orange Book product (application + product)
    return [replace("global:combo_sets", cset), replace("global:orange_book", ob), replace("global:ema", ema)]
