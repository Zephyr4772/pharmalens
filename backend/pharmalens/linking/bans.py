"""Roadmap #12: prohibited FDC notifications -> combinations (salt-form tolerant), as links; reg_banned_fdc and the
catalog's own ban flags are untouched.

The ban's combination text is resolved with the exact-dictionary molecule resolver (salt and form words are noise,
molecule keys fold salt forms: "Phenylephrine HCl" = "Phenylephrine"). A ban links to every combination whose
ingredient set equals the resolved set:
  complete_set     every ingredient in the text resolved (0.9, shown)
  partial_set      some words unexplained, but the resolved set equals a marketed combination's (0.7, inferred:
                   the unexplained word may be another ingredient, so the ban may be for a different combination)
Single-ingredient bans (e.g. a molecule banned outright) link to the molecule, not to combinations.
"""
from .. import db
from .molecules import _index, resolve
from .store import licence_of, replace


def run() -> dict:
    cur = db.cursor()
    idx = _index()
    from .hygiene import canon_map
    cmap = canon_map()
    sets: dict[str, list[str]] = {}
    for cid, st in cur.execute("SELECT src_key, dst_id FROM entity_links WHERE linker = 'global:combo_sets'").fetchall():
        sets.setdefault(st, []).append(cid)
    lic = licence_of("reg_banned_fdc", "combos")
    links = []
    for bid, text, notif, status in cur.execute("SELECT id, combo_text, notification, status FROM reg_banned_fdc").fetchall():
        found = [f for f in resolve(text or "", True, idx) if f[1] in ("complete", "partial")]
        if not found:
            continue
        ids = sorted({str(cmap.get(f[0], f[0])) for f in found}, key=int)
        complete = all(f[1] == "complete" for f in found)
        ev = f"“{text}” ({status}, {notif or 'notification n/a'}) resolved to " + " + ".join(f[3].split("'")[1] for f in found)
        if len(ids) == 1:
            links.append({"src_table": "reg_banned_fdc", "src_key": bid, "dst_type": "molecule", "dst_id": ids[0],
                          "method": "single_ingredient_ban", "confidence": 0.9 if complete else 0.7, "evidence": ev, "licence": lic})
            continue
        st = ",".join(ids)
        for cid in sets.get(st, []):
            links.append({"src_table": "reg_banned_fdc", "src_key": bid, "dst_type": "combo", "dst_id": cid,
                          "method": "complete_set" if complete else "partial_set", "confidence": 0.9 if complete else 0.7,
                          "evidence": ev, "licence": lic})
        if sets.get(st):
            links.append({"src_table": "reg_banned_fdc", "src_key": bid, "dst_type": "ingredient_set", "dst_id": st,
                          "method": "complete_set" if complete else "partial_set", "confidence": 0.9 if complete else 0.7,
                          "evidence": ev, "licence": lic})
    return replace("bans:combo", links)
