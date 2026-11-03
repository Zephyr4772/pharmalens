"""Roadmap #7: NSQ / spurious batch -> catalog SKU, and through the SKU its marketer and group.

A failed batch is a quality record, so it reaches a SKU only on several pieces of agreeing evidence:

  brand_set_maker      a brand named in the batch text (in brackets, or leading: "Rodal 650 (Paracetamol ...)") is the
                       SKU's brand, the ingredients agree, and the batch's manufacturer is related to the SKU (it is the
                       marketer, registered that brand under 84AB, or makes for that marketer)              0.95
  counterfeit_of_brand a SPURIOUS listing carrying a SKU's brand with agreeing ingredients: the batch is a fake of that
                       SKU, so the claimed manufacturer need not be related                                   0.85
  maker_set_unique     no brand, but the manufacturer is related to exactly one SKU with the same complete ingredient
                       set, strength and dosage form                                                        0.85
  brand_set_other_maker  brand and ingredients agree but the manufacturer is unrelated (a different firm's product of
                       the same name, or a spurious batch not yet listed as such)                            0.7, inferred
  maker_set_one_of_n   the manufacturer makes several matching SKUs; each is a candidate                     0.7, inferred
Ingredients agree when the batch's complete canonical set equals the SKU's, or (when the text did not resolve
completely) every resolved molecule is in the SKU. Strengths stated in the batch text must all appear in the SKU's
strengths or name; a stated dosage form must match the SKU's. reg_nsq is not modified.
"""
import re
from collections import defaultdict

import pandas as pd

from .. import db
from ..normalize import norm
from .hygiene import canon_map
from .molecules import NOISE, _index, resolve
from .store import HIGH, ensure, licence_of, replace

FORMS = [("tablet", r"\btab(?:let)?s?\b"), ("capsule", r"\bcap(?:sule)?s?\b|softgel"), ("injection", r"\binj(?:ection)?s?\b|\binfusion\b|\bvials?\b"),
         ("liquid", r"\bsyrup\b|\bsuspension\b|\boral (?:liquid|solution)\b|\belixir\b|\bdry syrup\b"),
         ("topical", r"\bcream\b|\bointment\b|\bgel\b|\blotion\b"), ("drops", r"\bdrops?\b"), ("powder", r"\bpowder\b|\bsachet\b|\bgranules\b")]
SKU_FORM = {"tablet": "tablet", "capsule": "capsule", "injection": "injection", "infusion": "injection", "syrup": "liquid", "suspension": "liquid",
            "solution": "liquid", "cream": "topical", "ointment": "topical", "gel": "topical", "lotion": "topical", "drop": "drops", "powder": "powder",
            "sachet": "powder", "granules": "powder"}
VARIANTS = {"sr", "xr", "er", "cr", "mr", "pr", "od", "forte", "plus", "ds", "xl", "la", "kid", "kids", "junior", "max", "fort"}
RELEASE_WORDS = {"sr", "xr", "er", "cr", "mr", "pr", "od", "xl", "la"}
NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|µg|g|gm|ml|iu|%|w/v|w/w)\b", re.I)


def form_of(text: str) -> str | None:
    t = (text or "").lower()
    return next((f for f, rx in FORMS if re.search(rx, t)), None)


def nums(text: str) -> set[float]:
    return {float(n) for n, _ in NUM.findall(text or "")}


def brand_words(text: str, mol_words: set[str]) -> list[tuple[str, str, str]]:
    """Candidate brands: bracketed segments and a leading segment that are not ingredient, strength or form text."""
    t = text or ""
    cands = re.findall(r"[(\[]([^()\[\]]{2,40})[)\]]", t)
    lead = re.split(r"[(\[,]", t, maxsplit=1)[0]
    if lead and lead != t:
        cands.append(lead)
    out = []
    for cnd in cands:
        toks = [x for x in norm(cnd).split() if x not in NOISE and not re.fullmatch(r"[\d.]+[a-z%]*", x)]
        if not toks:
            continue
        w1 = toks[0]
        if len(w1) < 4 or w1 in mol_words:
            continue
        bn = ",".join(re.findall(r"\d+(?:\.\d+)?", cnd.replace(" .", ".")))      # "RABEKIND-20", "Amoxyclav 625"
        out.append((w1, toks[1] if len(toks) > 1 and not toks[1][0].isdigit() else "", bn))
    return out


def run() -> dict:
    ensure()
    cur = db.cursor()
    idx = _index()
    cmap = canon_map()
    mol_words = {w for (n,) in cur.execute("SELECT lower(name) FROM molecules").fetchall() for w in norm(n).split()[:1]}
    mol_words |= {w for (k,) in cur.execute("SELECT mkey FROM molecules").fetchall() for w in (k or "").split()[:1]}
    maker_of = dict(cur.execute("SELECT src_key, dst_id FROM entity_links WHERE linker = 'maker:reg_nsq' AND confidence >= 0.85").fetchall())
    feats, brands = [], []
    for nid, cat, text in cur.execute("SELECT id, category, product_text FROM reg_nsq WHERE product_text IS NOT NULL").fetchall():
        bws = brand_words(text, mol_words)
        # resolve the ingredients without the brand words, so a branded batch can still have a complete set
        plain = " ".join(t for t in norm(text).split() if t not in {b[0] for b in bws} | {b[1] for b in bws if b[1]})
        found = resolve(plain, True, idx)
        ids = sorted({str(cmap.get(f[0], f[0])) for f in found if f[1] in ("complete", "partial")}, key=int)
        if not ids:
            continue
        complete = all(f[1] == "complete" for f in found)
        feats.append({"nsq_id": nid, "category": cat, "maker_key": maker_of.get(str(nid)), "set": ",".join(ids), "complete": complete,
                      "form": form_of(text), "nums": ",".join(str(x) for x in sorted(nums(text))), "text": text})
        for w1, w2, bn in bws:
            brands.append({"nsq_id": nid, "w1": w1, "w2": w2, "bnums": bn})
    nf, bf = pd.DataFrame(feats), pd.DataFrame(brands, columns=["nsq_id", "w1", "w2", "bnums"])
    c = db.cursor()
    c.register("_nf", nf)
    c.register("_bf", bf)
    # candidate SKUs: by brand word, or by a manufacturer related to the SKU, always with agreeing ingredients
    cand = c.execute(f"""
        WITH ps AS (SELECT CAST(src_key AS INTEGER) combo_id, dst_id s FROM entity_links WHERE linker = 'global:combo_sets'),
             p AS (SELECT p.id, p.company_id, p.name, p.name_norm, ps.s, lower(coalesce(p.dosage_form, '')) form,
                          split_part(p.name_norm, ' ', 1) w1, split_part(p.name_norm, ' ', 2) w2
                   FROM products p JOIN ps ON ps.combo_id = p.combo_id WHERE NOT coalesce(p.is_discontinued, false)),
             rel AS (SELECT maker_key, company_id, 'marketer' r FROM makers WHERE company_id IS NOT NULL
                     UNION SELECT maker_key, company_id, 'makes_for' FROM maker_makes_for),
             regp AS (SELECT ml.dst_id maker_key, CAST(bp.dst_id AS INTEGER) product_id FROM entity_links bp
                      JOIN entity_links ml ON ml.linker = 'maker:brand_registry' AND ml.src_key = bp.src_key
                      WHERE bp.linker = 'maker:brand_product'),
             by_brand AS (SELECT DISTINCT n.nsq_id, p.*, TRUE brand_hit, (b.w2 <> '' AND b.w2 = p.w2) brand_two, b.bnums, b.w2 bw2
                          FROM _bf b JOIN p ON p.w1 = b.w1 JOIN _nf n ON n.nsq_id = b.nsq_id
                          WHERE (n.complete AND p.s = n.set) OR (NOT n.complete AND list_has_all(string_split(p.s, ','), string_split(n.set, ',')))),
             by_maker AS (SELECT DISTINCT n.nsq_id, p.*, FALSE brand_hit, FALSE brand_two, '' bnums, '' bw2 FROM _nf n
                          JOIN (SELECT maker_key, company_id FROM rel) r ON r.maker_key = n.maker_key
                          JOIN p ON p.company_id = r.company_id AND p.s = n.set WHERE n.complete
                          UNION
                          SELECT DISTINCT n.nsq_id, p.*, FALSE, FALSE, '', '' FROM _nf n JOIN regp ON regp.maker_key = n.maker_key
                          JOIN p ON p.id = regp.product_id AND p.s = n.set WHERE n.complete)
        SELECT x.*, (EXISTS (SELECT 1 FROM _nf n JOIN rel ON rel.maker_key = n.maker_key WHERE n.nsq_id = x.nsq_id AND rel.company_id = x.company_id)
                     OR EXISTS (SELECT 1 FROM _nf n JOIN regp ON regp.maker_key = n.maker_key WHERE n.nsq_id = x.nsq_id AND regp.product_id = x.id)) related,
               (SELECT string_agg(pm.strength, ' ') FROM product_molecules pm WHERE pm.product_id = x.id) strengths
        FROM (SELECT * FROM by_brand UNION ALL SELECT * FROM by_maker) x""").fetchall()
    cols = ["nsq_id", "id", "company_id", "name", "name_norm", "s", "form", "w1", "w2", "brand_hit", "brand_two", "bnums", "bw2", "related", "strengths"]
    c.unregister("_nf")
    c.unregister("_bf")
    info = {f["nsq_id"]: f for f in feats}
    branded = {b["nsq_id"] for b in brands}
    by_nsq: dict[int, list[dict]] = defaultdict(list)
    for r in cand:
        d = dict(zip(cols, r))
        by_nsq[d["nsq_id"]].append(d)
    lic = licence_of("reg_nsq", "products")
    links = []
    for nid, cs in by_nsq.items():
        f = info[nid]
        want = {float(x) for x in f["nums"].split(",") if x}
        best: dict[int, dict] = {}
        for d in cs:        # one row per SKU: brand evidence wins over maker-only evidence
            if d["id"] not in best or (d["brand_hit"] and not best[d["id"]]["brand_hit"]):
                best[d["id"]] = d
        ok = []
        for d in best.values():
            sku_form = next((v for k, v in SKU_FORM.items() if k in d["form"]), None)
            if f["form"] and sku_form and f["form"] != sku_form:
                continue
            name_nums = {float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])", d["name"] or "")}
            have = nums(d["strengths"] or "") | name_nums
            if want and not want <= have:
                continue
            if d["brand_hit"]:
                # the SKU's variant word after the brand ("Telma-MCT", "Xykaa Rapid") must be the batch's ("Telma H": no)
                sku_w2 = d["w2"] if d["w2"] and d["w2"].isalpha() and d["w2"] not in NOISE and d["w2"] not in SKU_FORM else ""
                if sku_w2 and sku_w2 != (d.get("bw2") or ""):
                    continue
            bwant = [float(x) for x in (d["bnums"] or "").split(",") if x]
            if d["brand_hit"] and bwant:
                # the number after the brand is its strength ("Rosuvas 10" != "Rosuvas 20Mg Tablet 10 S", whose 10 is the pack)
                first = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])", d["name"] or "")
                if first and float(first.group(1)) != bwant[0]:
                    continue
                if not set(bwant) <= have:
                    continue                  # "RABEKIND-20" is not "Rabekind 40"
            d["sig"] = tuple(sorted(have))
            ok.append(d)
        # release / strength variants on the SKU need support in the batch text ("Okamet 500" is not "Okamet 500 SR")
        t = norm(f["text"])
        released = bool(re.search(r"prolonged|sustained|extended|controlled|modified|release", t))
        def variant_ok(d):
            for v in VARIANTS & set(norm(d["name"]).split()):
                if v in t.split() or (v in RELEASE_WORDS and released):
                    continue
                return False
            return True
        ok = [d for d in ok if variant_ok(d)]
        brand = [d for d in ok if d["brand_hit"]]
        exact = [d for d in brand if d.get("bw2") and d["w2"] == d["bw2"]]
        if exact:
            brand = exact                     # "DYNAPAR AQ": keep "Dynapar AQ", drop plain "Dynapar 75mg"
        spurious = f["category"] == "SPURIOUS"
        named = nid in branded                # the batch names a brand (whether or not it is in the catalog)
        out = []
        # a brand without any stated strength that matches SKUs of different strengths does not say which one
        unsure = bool(brand) and not want and not any(d["bnums"] for d in brand) and len({d["sig"] for d in brand}) > 1
        if brand:
            for d in brand:
                if unsure:
                    out.append((d, "brand_strength_unknown", 0.7))
                elif d["related"]:
                    out.append((d, "brand_set_maker", 0.95))
                elif spurious:
                    out.append((d, "counterfeit_of_brand", 0.85))
                else:
                    out.append((d, "brand_set_other_maker", 0.7))
        else:
            rel = [d for d in ok if d["related"]]
            if len(rel) == 1 and want and not named:
                out.append((rel[0], "maker_set_unique", 0.85))
            elif named:
                # the batch names a brand the catalog lacks: another brand of the same maker is not this batch
                out += [(d, "brand_not_in_catalog", 0.6) for d in rel]
            else:
                out += [(d, "maker_set_one_of_n" if len(rel) > 1 else "maker_set_no_strength", 0.7) for d in rel]
        for d, method, conf in out:
            links.append({"src_table": "reg_nsq", "src_key": nid, "dst_type": "product", "dst_id": d["id"], "method": method, "confidence": conf,
                          "evidence": f"“{f['text'][:110]}” ({f['category']}; maker {(f['maker_key'] or '?')[3:]}) -> “{d['name']}”"
                                      + (f"; brand '{d['w1']}'" if d["brand_hit"] else "") + ("; maker related" if d["related"] else "; maker unrelated")
                                      + (f"; strengths {f['nums']}" if f["nums"] else ""),
                          "licence": lic})
    return replace("nsq:product", links, note=f"{len(feats):,} batches with resolved ingredients; {len(by_nsq):,} with candidates")
