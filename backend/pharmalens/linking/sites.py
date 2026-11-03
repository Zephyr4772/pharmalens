"""Plant stage 2: manufacturing sites (sites), from the addresses the records carry.

A site is one maker (firm key, see makers.py) at one place: in India its PIN code, abroad its country and postal code.
Units of one firm that share a PIN are one site here; their unit labels are kept. Sources, with the role of the site:
  reg_approvals.sites        manufacturing sites named in a CDSCO approval (one approval may name several)
  reg_nsq.manufacturer       the site whose batch failed (firm name + address)
  firm_debarments.address    the debarred firm's address
  usfda_actions              import-alert address (subject) / recall city (event payload): these carry no PIN
  fda_inspections            US FDA inspection (FEI, firm, street, city; abroad state + ZIP), when loaded
  fda_compliance_actions     US FDA warning letter / injunction (same fields), makers or inspected FEIs only
  fda_import_refusals        US FDA refused drug shipment from India (same fields), makers or inspected FEIs only
Records with a PIN link to their site at 0.9 (the site is defined by the record's own address). Records without one
link to the maker's PIN site whose address shares their locality words when exactly one such site exists (0.85,
locality_match); otherwise to a district-level site of that maker (0.85, district_site: "this firm's plant in district
X"), or, with no recognisable district, not at all. Sites inherit the maker's company and group. Sources unchanged.
"""
import json
import re
from collections import Counter, defaultdict

import pandas as pd

from .. import db
from ..normalize import norm
from .companies import distinctive, strict_key
from .makers import clean
from .store import ensure, licence_of

STATES = ["andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand",
          "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
          "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand", "uttaranchal", "west bengal", "delhi",
          "jammu and kashmir", "jammu", "puducherry", "pondicherry", "chandigarh", "daman", "dadra", "ladakh", "h p", "hp", "u p", "m p"]
GENERIC = set("""plot no road industrial estate area village district dist mandal taluka tal tehsil near opp opposite sector phase gidc midc
ida sidcul ltd limited pvt private unit block survey sy khasra floor building complex highway nagar park zone sez post po via
behind main cross lane street st the and of at in india state town city new old ground first second third m s ms co""".split()) | {s for st in STATES for s in st.split()}
PIN = re.compile(r"(?<!\d)([1-8]\d{2})\s?-?\s?(\d{3})(?!\d)")
FOREIGN = re.compile(r"\b([A-Za-z][A-Za-z .()]+?)\s*-\s*([A-Za-z0-9][A-Za-z0-9 -]{2,11})\s*$")
PERSON = re.compile(r"^\s*(?:dr|mr|mrs|ms|prof)\.?\s|\b(?:m\.?\s?d|ph\.?\s?d|mbbs)\.?\s*$", re.I)   # BIMO clinical investigators
NOT_A_FIRM = re.compile(r"^\s*(?:other\s+site|site|plant|factory|manufacturing\s+site|address|plot|unit|premises)\b", re.I)

DDL = """
CREATE TABLE IF NOT EXISTS sites (
    site_key    VARCHAR PRIMARY KEY,   -- 'st:<maker key>|<PIN>' / '|<country>:<postal>' / '|<state>:<district>'
    maker_key   VARCHAR,
    maker_name  VARCHAR,
    kind        VARCHAR,               -- pin | foreign_postal | district
    country     VARCHAR,
    pin         VARCHAR,
    state       VARCHAR,
    locality    VARCHAR,               -- distinctive address words seen for this site
    address     VARCHAR,               -- the most frequent address text
    units       VARCHAR,               -- unit / plant labels seen ("Unit II")
    records     INTEGER,
    roles       VARCHAR,               -- JSON {role: records}
    company_id  INTEGER,
    parent_id   INTEGER,
    auto_group  VARCHAR
);
ALTER TABLE sites ADD COLUMN IF NOT EXISTS fei VARCHAR;   -- US FDA establishment ids seen for this site (inspections feed)
"""


def _r(a, b):
    return {str(x) for x in range(a, b + 1)}


# a PIN's first two digits by state (India Post zones); old Andhra addresses keep Hyderabad's 50
PIN_STATE = {"delhi": {"11"}, "haryana": {"12", "13"}, "punjab": {"14", "15", "16"}, "chandigarh": {"16"}, "himachal pradesh": {"17"},
             "jammu and kashmir": {"18", "19"}, "jammu": {"18", "19"}, "ladakh": {"19"}, "uttar pradesh": _r(20, 28), "uttarakhand": {"24", "26"},
             "uttaranchal": {"24", "26"}, "rajasthan": _r(30, 34), "gujarat": _r(36, 39), "daman": {"39"}, "dadra": {"39"},
             "maharashtra": _r(40, 44), "goa": {"40"}, "madhya pradesh": _r(45, 48), "chhattisgarh": {"49"}, "telangana": {"50"},
             "andhra pradesh": _r(50, 53), "karnataka": _r(56, 59), "tamil nadu": _r(60, 64), "puducherry": {"60", "53", "67"},
             "pondicherry": {"60", "53", "67"}, "kerala": _r(67, 69), "west bengal": _r(70, 74), "sikkim": {"73"}, "odisha": _r(75, 77),
             "orissa": _r(75, 77), "assam": {"78"}, "arunachal pradesh": {"79"}, "manipur": {"79"}, "meghalaya": {"79"}, "mizoram": {"79"},
             "nagaland": {"79"}, "tripura": {"79"}, "bihar": _r(80, 85), "jharkhand": _r(80, 85)}


def pin_of(text: str) -> str | None:
    """The last PIN-shaped number that fits a state the address names ("4-1-424-426 Bank Street, Hyderabad, Telangana" has none)."""
    m = [x.group(1) + x.group(2) for x in PIN.finditer(text or "")]
    t = f" {norm(text)} "
    ok = set().union(*[v for s, v in PIN_STATE.items() if f" {s} " in t])
    if ok:
        m = [p for p in m if p[:2] in ok]
    return m[-1] if m else None


def state_of(text: str) -> str | None:
    t = f" {norm(text)} "
    return next((s for s in STATES if f" {s} " in t and len(s) > 3), None)


def locality(text: str) -> set[str]:
    return {w for w in norm(re.sub(r"\d", " ", text or "")).split() if len(w) >= 4 and w not in GENERIC}


def district(text: str) -> str | None:
    """The place just before the state ("..., Vadodara, Gujarat INDIA" -> vadodara; "District Solan" -> solan)."""
    m = re.search(r"\bdist(?:rict)?\.?\s+([A-Za-z]+)", text or "", re.I)
    if m:
        return m.group(1).lower()
    segs = [s.strip() for s in re.split(r",", text or "") if s.strip()]
    for i, seg in enumerate(segs):
        if state_of(seg) and i > 0:
            w = [x for x in norm(re.sub(r"\d", " ", segs[i - 1])).split() if x not in GENERIC and len(x) >= 4]
            return w[-1] if w else None
    w = [x for x in norm(re.sub(r"\d", " ", segs[-1] if segs else "")).split() if x not in GENERIC and len(x) >= 4]
    return w[-1] if w else None


def unit_of(text: str) -> str | None:
    m = re.search(r"\bunit\s*[-:]?\s*([ivx]+|\d+|[a-z])\b", text or "", re.I)
    return f"Unit {m.group(1).upper()}" if m else None


def run() -> dict:
    ensure()
    with db.writer() as w:
        w.execute(DDL)
    cur = db.cursor()
    makers = {k: (n, c, p, a, d) for k, n, c, p, a, d in cur.execute(
        "SELECT maker_key, name, company_id, parent_id, auto_group, distinctive FROM makers").fetchall()}
    maker_link = {}
    for lk, sk, mk in cur.execute("""SELECT linker, src_key, dst_id FROM entity_links WHERE linker IN ('maker:reg_nsq', 'maker:usfda_actions',
                                     'maker:firm_debarments')""").fetchall():
        maker_link[(lk.split(":")[1], sk)] = mk
    recs = []      # (table, src_key, maker_key, address, role, country)

    def mk_from(name):
        if NOT_A_FIRM.search(name or ""):
            return None                    # "Other Site, ...": the approval lists an address without a firm name
        # foreign firms end at their legal suffix; text after it is a product or a plant ("... GmbH & Co KG Fitusiran 50 mg")
        m = re.search(r"\b(?:gmbh(?:\s*(?:&|and)\s*co\.?)?(?:\s*kg)?|kg|ag|s\.?\s?a\.?|s\.?p\.?a\.?|llc|l\.?p\.?|b\.?v\.?|n\.?v\.?|plc|pty|oy|ab|sas|s\.?l\.?|corp(?:oration)?|inc)\b\.?",
                      name or "", re.I)
        if m:
            name = name[:m.end()]
        k = strict_key(clean(name or ""))
        return "mk:" + k if len(k) >= 3 else None

    for aid, sites in cur.execute("SELECT id, sites FROM reg_approvals WHERE sites IS NOT NULL").fetchall():
        for s in json.loads(sites or "[]"):
            firm = re.split(r",", s, maxsplit=1)[0]
            recs.append(("reg_approvals", str(aid), mk_from(firm), s, "approved_site", None))
    for nid, mf in cur.execute("SELECT id, manufacturer FROM reg_nsq WHERE manufacturer IS NOT NULL").fetchall():
        recs.append(("reg_nsq", str(nid), maker_link.get(("reg_nsq", str(nid))), mf, "batch_site", "India"))
    for key, firm, addr in cur.execute("SELECT dedupe_key, firm, address FROM firm_debarments WHERE address IS NOT NULL").fetchall():
        recs.append(("firm_debarments", key, maker_link.get(("firm_debarments", key)) or mk_from(firm), addr, "debarred_site", "India"))
    fei_of: dict[tuple, str] = {}
    fda_city: dict[tuple, tuple] = {}
    FDA = {   # FDA Data Dashboard tables: FEI + firm + street / city / state / ZIP (abroad); an Indian address has a city only
        "fda_inspections": ("us_fda_inspection", """SELECT inspection_id, fei, firm, address, city, state, zip, country, project_area
                                                      FROM fda_inspections"""),
        "fda_compliance_actions": ("us_fda_compliance", """SELECT case_id, fei, firm, address, city, state, zip, country, NULL
                                                             FROM fda_compliance_actions"""),
        "fda_import_refusals": ("us_fda_refusal", """SELECT shipment_id || '|' || product_code, fei, firm, address, city, NULL, NULL, country, NULL
                                                       FROM fda_import_refusals"""),
    }
    inspected: set[str] = set()
    for table, (role, sql) in FDA.items():
        try:
            rows_ = cur.execute(sql).fetchall()
        except Exception:  # noqa: BLE001 — feed not loaded yet
            continue
        for iid, fei, firm, street, cty, st, z, ctry, area in rows_:
            india = bool(re.search(r"india", ctry or "", re.I))
            mk = mk_from(firm)
            if not mk or PERSON.search(firm or "") or (re.search(r"bioresearch", area or "", re.I) and mk not in makers):
                continue           # clinical investigators, hospitals and CROs (BIMO) are not plants, unless the firm is a known maker
            if table == "fda_inspections":
                inspected.add(fei)
            elif mk not in makers and fei not in inspected:
                continue           # warning letters and refused shipments also reach traders and web shops: only makers or inspected plants
            if india:              # FDA gives Indian firms no PIN; the street's numbers are survey / plot numbers, never a PIN
                street = re.sub(r"\d", " ", street or "")
            addr = (f"{street}, {cty or ''}, {st or ''} {z or ''}, India" if india
                    else f"{street or ''}, {cty or ''}, {st or ''}, {ctry or ''}-{z or ''}")
            recs.append((table, str(iid), mk, addr, role, "India" if india else (ctry or "")))
            fei_of[(table, str(iid))] = fei
            if india:
                fda_city[(table, str(iid))] = (street, cty)
    # FDA's Indian addresses carry a city but no state or PIN: take the state our other Indian addresses give that place, when they agree
    place_state: dict[str, Counter] = defaultdict(Counter)
    for table, sk, mk, addr, role, country in recs:
        st, d = state_of(addr), district(addr)
        if table not in FDA and st and d:
            place_state[d][st] += 1
    for n, (table, sk, mk, addr, role, country) in enumerate(recs):
        if (table, sk) not in fda_city or state_of(addr) or pin_of(addr):
            continue
        street, cty = fda_city[(table, sk)]
        for part in reversed([p.strip() for p in re.split(r"[,(]", cty or "") if p.strip()]):     # "Gajraula, Amroha" -> amroha, then gajraula
            words = [w for w in norm(part).split() if w not in GENERIC and len(w) >= 4]
            c = place_state.get(words[-1]) if words else None
            if c and c.most_common(1)[0][1] >= 0.9 * sum(c.values()):
                recs[n] = (table, sk, mk, f"{street or ''}, {part}, {c.most_common(1)[0][0].title()}, India", role, country)
                break
    city = dict(cur.execute("""SELECT split_part(dedupe_key, '|', 2), json_extract_string(payload, '$.city') FROM events
                               WHERE dedupe_key LIKE 'fda|recall-%'""").fetchall())
    for aid, kind, firm, country, subject in cur.execute("SELECT id, kind, firm, country, subject FROM usfda_actions").fetchall():
        addr = subject.split("—", 1)[1] if kind == "import_alert" and "—" in (subject or "") else (city.get(str(aid)) or "")
        if addr:
            recs.append(("usfda_actions", str(aid), maker_link.get(("usfda_actions", str(aid))) or mk_from(firm), f"{addr}, {country or ''}",
                         "us_fda_site", country))
    # pass 1: sites with a PIN (India) or a postal code (abroad)
    site_of: dict[tuple, str] = {}
    info: dict[str, dict] = {}
    pending = []
    recs.sort(key=lambda r: list(FDA).index(r[0]) + 1 if r[0] in FDA else 0)   # stable: FDA tables after the sources that define sites, inspections first
    for table, sk, mk, addr, role, country in recs:
        if not mk:
            continue
        foreign = (country and not re.search(r"india", country, re.I)) or (table == "reg_approvals" and not re.search(r"\bindia\b", addr, re.I))
        if foreign and state_of(addr) and pin_of(addr):
            foreign = False                # "..., Punjab Toansa Iran-144533": an Indian state and a PIN, the country is a typo
        key = kind = None
        if foreign:
            m = FOREIGN.search(addr)
            if m and (table == "reg_approvals" or table in FDA):
                ctry = norm(m.group(1)).split()[-1] if norm(m.group(1)) else ""
                key, kind, country = f"st:{mk[3:]}|{ctry}:{norm(m.group(2)).replace(' ', '')}", "foreign_postal", m.group(1).strip()
                if table in FDA and key not in info:
                    key = None     # abroad, inspections only join a site our India-facing sources already list (US parents share names)
        else:
            p = pin_of(addr)
            if p:
                key, kind, country = f"st:{mk[3:]}|{p}", "pin", "India"
        if key:
            site_of[(table, sk, addr)] = key
            s = info.setdefault(key, {"maker_key": mk, "kind": kind, "country": country, "pin": key.split("|")[1] if kind == "pin" else None,
                                      "addr": Counter(), "loc": Counter(), "units": set(), "roles": Counter(), "state": Counter(), "fei": set()})
            if fei_of.get((table, sk)):
                s["fei"].add(fei_of[(table, sk)])
            s["addr"][addr.strip()[:200]] += 1
            s["loc"].update(locality(addr))
            s["roles"][role] += 1
            if unit_of(addr):
                s["units"].add(unit_of(addr))
            if state_of(addr):
                s["state"][state_of(addr)] += 1
        else:
            pending.append((table, sk, mk, addr, role, country))
    # pass 2: records without a PIN: the maker's single PIN site sharing their locality words, else a district site
    by_maker: dict[str, list[str]] = defaultdict(list)
    for k, s in info.items():
        if s["kind"] == "pin":
            by_maker[s["maker_key"]].append(k)
    method_of: dict[tuple, tuple[str, float]] = {}
    fei_sites: dict[str, set] = defaultdict(set)      # FEI -> sites placed so far (FDA's establishment id: one plant)

    def fits(addr, mk, key):
        """FDA files one FEI under different addresses now and then: join by FEI only when the record's place agrees with the site's."""
        s, st = info[key], state_of(addr)
        if st and s["state"] and st not in s["state"]:
            return False
        loc = locality(addr) - set(mk[3:].split())
        return not loc or not s["loc"] or bool(loc & set(s["loc"]))

    for (table, sk, addr), key in site_of.items():
        if fei_of.get((table, sk)):
            fei_sites[fei_of[(table, sk)]].add(key)
    for table, sk, mk, addr, role, country in pending:
        f = fei_of.get((table, sk))
        if f and len(fei_sites.get(f, ())) == 1 and fits(addr, mk, next(iter(fei_sites[f]))):
            key = next(iter(fei_sites[f]))
            site_of[(table, sk, addr)] = key
            method_of[(table, sk, addr)] = ("same_fei", 0.95)
            info[key]["roles"][role] += 1
            continue
        loc = locality(addr) - set(mk[3:].split())     # the firm's own name in its street ("Dabur India Ltd, ...") is not a place
        rec_state = state_of(addr)
        scores = [(len(loc & set(info[k]["loc"])), k) for k in by_maker.get(mk, [])
                  if not (rec_state and info[k]["state"] and rec_state not in info[k]["state"])]   # never across states
        scores = [x for x in scores if x[0] > 0]
        best = max((x[0] for x in scores), default=0)
        top = [k for n, k in scores if n == best]
        if len(top) == 1:
            site_of[(table, sk, addr)] = top[0]
            method_of[(table, sk, addr)] = ("locality_match", 0.85)
            info[top[0]]["roles"][role] += 1
            if f:
                fei_sites[f].add(top[0])
            continue
        dist, st = district(addr), state_of(addr)
        foreign = (country and not re.search(r"india", country, re.I)) or (table == "reg_approvals" and not re.search(r"india", addr, re.I))
        if not dist or foreign:
            continue                       # abroad without a postal code: no reliable site
        key = f"st:{mk[3:]}|{st or 'india'}:{dist}"
        if table in ("fda_compliance_actions", "fda_import_refusals") and key not in info:
            continue                       # a shipper's or addressee's office is not a plant: these only join sites other records define
        site_of[(table, sk, addr)] = key
        method_of[(table, sk, addr)] = ("district_site", 0.85)
        if f:
            fei_sites[f].add(key)
        s = info.setdefault(key, {"maker_key": mk, "kind": "district", "country": "India", "pin": None, "addr": Counter(), "loc": Counter(),
                                  "units": set(), "roles": Counter(), "state": Counter(), "fei": set()})
        s["addr"][addr.strip()[:200]] += 1
        s["loc"].update(loc)
        s["roles"][role] += 1
        if st:
            s["state"][st] += 1
    # pass 3: an FEI is FDA's id for one establishment, so inspections sharing it share the site, when the placed ones agree
    by_fei: dict[str, set] = defaultdict(set)
    for (table, sk, addr), key in site_of.items():
        if fei_of.get((table, sk)):
            by_fei[fei_of[(table, sk)]].add(key)
    for table, sk, mk, addr, role, country in pending:
        f = fei_of.get((table, sk))
        if (table, sk, addr) in site_of or not f or len(by_fei.get(f, ())) != 1 or not fits(addr, mk, next(iter(by_fei[f]))):
            continue
        key = next(iter(by_fei[f]))
        site_of[(table, sk, addr)] = key
        method_of[(table, sk, addr)] = ("same_fei", 0.95)
        info[key]["roles"][role] += 1
    for (table, sk, addr), key in site_of.items():
        if fei_of.get((table, sk)):
            info[key]["fei"].add(fei_of[(table, sk)])
    rows = []
    for k, s in info.items():
        n, cid, pid, ag, dist_ = makers.get(s["maker_key"], (None, None, None, None, True))
        rows.append({"site_key": k, "maker_key": s["maker_key"], "maker_name": n or s["maker_key"][3:].title(), "kind": s["kind"], "country": s["country"],
                     "pin": s["pin"], "state": s["state"].most_common(1)[0][0].title() if s["state"] else None,
                     "locality": ", ".join(w for w, _ in s["loc"].most_common(6)), "address": s["addr"].most_common(1)[0][0],
                     "units": ", ".join(sorted(s["units"])) or None, "records": sum(s["roles"].values()), "roles": json.dumps(dict(s["roles"])),
                     "fei": ", ".join(sorted(s.get("fei", set()))) or None,
                     "company_id": cid, "parent_id": pid, "auto_group": ag})
    sdf = pd.DataFrame(rows)
    links = []
    for (table, sk, addr), key in site_of.items():
        mth, conf = method_of.get((table, sk, addr), ("address_pin" if info[key]["kind"] == "pin" else "address_postal", 0.9))
        mk = info[key]["maker_key"]
        if not makers.get(mk, (None, None, None, None, True))[4]:
            conf, mth = 0.7, mth + ":generic_firm_name"
        links.append((table, sk, "site", key, mth, conf, f"“{addr.strip()[:150]}” -> {key[3:]}", licence_of(table)))
    ldf = pd.DataFrame(links, columns=["src_table", "src_key", "dst_type", "dst_id", "method", "confidence", "evidence", "licence"]).drop_duplicates(
        ["src_table", "src_key", "dst_id"])
    with db.writer() as w:
        w.execute("DELETE FROM sites").fetchall()
        w.register("_s", sdf)
        w.execute("""INSERT INTO sites (site_key, maker_key, maker_name, kind, country, pin, state, locality, address, units, records, roles,
                     company_id, parent_id, auto_group, fei)
                     SELECT site_key, maker_key, maker_name, kind, country, pin, state, locality, address, units, records::INTEGER, roles,
                     company_id::INTEGER, parent_id::INTEGER, auto_group, fei FROM _s""").fetchall()
        w.unregister("_s")
        w.execute("DELETE FROM entity_links WHERE linker = 'site:records'").fetchall()
        w.register("_l", ldf)
        w.execute("""INSERT INTO entity_links SELECT 'site:records', src_table, src_key, dst_type, dst_id, method, confidence, evidence, licence, now()
                     FROM _l ON CONFLICT DO NOTHING""").fetchall()
        w.unregister("_l")
        kinds = dict(Counter(sdf.kind))
        w.execute("INSERT INTO linker_runs VALUES ('sites', now(), now(), ?, ?, ?)", [len(sdf), len(ldf), json.dumps(kinds)]).fetchall()
    return {"linker": "sites", "links": len(ldf), "sites": len(sdf), "kinds": kinds}
