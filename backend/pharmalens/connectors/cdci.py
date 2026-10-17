"""Common Drug Codes for India (CDCI) — the national drug terminology from NRCeS / C-DAC.

Licence: CC BY 4.0 (redistribution and derivatives permitted within India), © C-DAC Pune.
Official flat files require registration at nrces.in; until credentials are configured
(CDCI_BASE_URL in .env) the July 2026 release is read from a public GitHub copy.

Loads brand, generic (with indication / contraindication / interactions / classification),
substance (CAS, UNII, SMILES, InChI, formula, toxicity), supplier, product, dose form and
route masters, then links substances to catalog molecules by name.
"""
import io
import os
import re
from datetime import date

import pandas as pd

from .. import db
from ..normalize import molecule_key
from .base import Connector

MIRROR = "https://raw.githubusercontent.com/dhananjaydpatkar/cdci_graph/HEAD/seed_data/CDCI202607/"
FILES = {
    "cdci_brand": "BrandMaster.txt", "cdci_generic": "GenericMaster.txt", "cdci_substance": "SubstanceMaster.txt",
    "cdci_supplier": "SupplierMaster.txt", "cdci_product": "ProductMaster.txt", "cdci_doseform": "DrugFormMaster.txt",
    "cdci_route": "RouteOfAdministrationMaster.txt",
}


def snake(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_")


class Cdci(Connector):
    name = "cdci"
    title = "Common Drug Codes for India (NRCeS / C-DAC)"
    agency = "NRCeS / C-DAC"
    schedule = {"trigger": "cron", "day": 3, "hour": 4, "minute": 0}
    description = "National drug terminology: brands, generics with indications/contraindications/interactions, substances with CAS/UNII/SMILES, suppliers."

    def run(self):
        base = os.getenv("CDCI_BASE_URL") or MIRROR
        counts = {}
        frames = {}
        for table, fname in FILES.items():
            r = self.get(base + fname, timeout=300)
            r.raise_for_status()
            self.archive(r.content, "txt", key=f"{table}-{date.today():%Y%m%d}")
            text = r.content.decode("utf-8-sig", errors="replace")
            ncols = len(text.split("\n", 1)[0].split("\t"))
            # free-text columns occasionally carry stray tabs: fold the overflow into the last column instead of dropping the row
            df = pd.read_csv(io.StringIO(text), sep="\t", dtype=str, keep_default_na=False, quoting=3, engine="python", index_col=False,
                             on_bad_lines=lambda f: f[:ncols - 1] + [" ".join(f[ncols - 1:])])
            df = df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed")]]
            df.columns = [snake(c) for c in df.columns]
            df = df.replace({"": None})
            frames[table] = df
            counts[table] = len(df)
        # link substances to catalog molecules
        mol = dict(db.cursor().execute("SELECT mkey, id FROM molecules").fetchall())
        sub = frames["cdci_substance"]
        sub["molecule_id"] = [mol.get(molecule_key(n)) if isinstance(n, str) else None for n in sub["substance_name"]]
        # brand rows: 'Safedox (cefpodoxime) 200 mg film-coated oral tablet' -> brand 'Safedox'
        br = frames["cdci_brand"]
        br["brand_short"] = [re.split(r"\s*\(", n, maxsplit=1)[0].strip() if isinstance(n, str) else None for n in br["brand_name"]]
        with db.writer() as w:
            for table, df in frames.items():
                w.execute(f"DROP TABLE IF EXISTS {table}")
                w.register("_cdci", df)
                w.execute(f"CREATE TABLE {table} AS SELECT * FROM _cdci")
                w.unregister("_cdci")
        self.stats.rows_seen = self.stats.rows_new = sum(counts.values())
        linked = int(sub["molecule_id"].notna().sum())
        self.stats.notes.append(" · ".join(f"{k.replace('cdci_', '')} {v:,}" for k, v in counts.items())
                                + f" · {linked:,} substances linked to catalog molecules"
                                + (" · source: GitHub mirror of 2026-07 release" if base == MIRROR else ""))
