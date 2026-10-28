# What DrugDen may sell

Reviewed 2026-10-28 from each source's published terms. The machine-readable version is
`backend/pharmalens/licensing.py`; the API and public samples (Hugging Face) must check `sellable(table)` before
serving anything. **Not legal advice: have a lawyer confirm this before launch.**

## The short version

| Class | Meaning | Tables |
|---|---|---|
| **Open** | Reuse freely (credit appreciated) | US FDA data: approvals, Orange Book, NDC, patents, recalls, shortages, import alerts; our corporate-group map |
| **Attribution** | Sellable with the stated credit (and conditions) | CDCI terminology (India only), ClinicalTrials.gov, EMA register, ChEMBL fields (share-alike), manufacturers' price lists |
| **Gazette** | Published in the Official Gazette: reproduction is not infringement | Prohibited FDCs, NPPA ceiling prices (+ history), NPPA new-drug launch prices, NLEM |
| **Permission** | Needs written permission from the agency first | CDSCO NSQ/spurious batches, approvals, SEC, document index, brand registry, new-brand dates; Jan Aushadhi; state tender rates; UP blacklist; PvPI alerts |
| **Internal** | Never sold or published | The product catalog (names, MRPs, packs, label text, interactions), molecules/combos/companies as derived from it, market-share estimates, WHO data, NSE market data, news headlines, DrugSetu |

**The headline problem: the product catalog is not ours to sell.** It is assembled from 17 Kaggle datasets that
include non-commercial (CC BY-NC-SA) and unlicensed sets scraped from 1mg, Apollo and Netmeds; the dataset's own
documentation says to "treat it as non-commercial and share-alike unless you rebuild without them". The 2025 MRPs
(~246k products) come from a CC BY-NC-SA 1mg scrape. Market-share estimates are computed from that catalog.

## Source by source

| Source | Terms found | Class | Evidence |
|---|---|---|---|
| CDSCO (cdsco.gov.in, cdscoonline.gov.in) | "The contents of this website may not be reproduced partially or fully, without due permission"; acknowledge the source; no misleading use | Permission | [CDSCO copyright policy](https://cdsco.gov.in/opencms/opencms/en/Copyright-Policy/) |
| Gazette of India (NPPA S.O. orders, FDC bans, ceiling prices, NLEM schedule) | Copyright Act 1957 s.52(1)(q)(i): reproducing matter published in the Official Gazette (other than Acts) is not infringement | Gazette | statute |
| NPPA website / IPDMS | no reuse policy found on the site | Permission (until confirmed) | — |
| State corporations, IPC/PvPI, PMBI | Indian government sites typically allow reproduction with permission and acknowledgement; not individually confirmed | Permission | [GST Council example](https://gstcouncil.gov.in/en/copyright-policy), [Income Tax example](https://www.incometaxindia.gov.in/en/copyright-policy) |
| CDCI (NRCeS / C-DAC) | CC BY 4.0; "can redistribute this package within India" and create derivatives within India; brand names belong to their owners; SNOMED CT parts follow the SNOMED affiliate licence | Attribution, India only | License.txt shipped with the release |
| openFDA | CC0 1.0 public domain unless noted | Open | [openFDA licence](https://open.fda.gov/license) |
| ClinicalTrials.gov | NLM data available at no charge; attribution expected | Attribution | [terms](https://classic.clinicaltrials.gov/ct2/about-site/terms-conditions) |
| EMA | reproduction "for commercial as well as non-commercial purposes provided that EMA is always acknowledged", in each copy | Attribution | [EMA legal notice](https://www.ema.europa.eu/en/about-us/legal-notice) |
| ChEMBL | CC BY-SA 3.0: credit, and redistributed derivatives of those fields stay CC BY-SA | Attribution (share-alike) | [ChEMBL](https://en.wikipedia.org/wiki/ChEMBL) |
| WHO (prequalification, alerts) | CC BY-NC-SA 3.0 IGO; "not for sale or for use in conjunction with commercial purposes"; commercial use needs WHO permission | Internal | [WHO copyright](https://www.who.int/copyright), [WHO terms](https://wkc.who.int/general/terms-of-use) |
| NSE (quotes, history, fundamentals, announcements) | NSE owns its market data; redistribution needs an NSE data agreement and fees | Internal | [NSE data policy](https://www.nseindia.com/market-data/nse-data-policy) |
| GDELT | open for academic, commercial and governmental use with citation | Attribution | [GDELT about](https://www.gdeltproject.org/about.html) |
| News headlines | publishers' copyright | Internal (terminal shows headline + link) | — |
| Manufacturers' Form V price lists | statutory price lists every manufacturer must issue and display (DPCO 2013 para 24); prices are facts, cite the document | Attribution | DPCO 2013 |
| Kaggle catalog datasets | mix of CC0, MIT, Apache 2.0, CC BY-SA, **CC BY-NC-SA, "Unknown", "© original authors"** | Internal | master dataset SOURCES.csv |
| DrugSetu | trial API access | Internal | — |

## What to do about it

1. **Write to CDSCO and NPPA** asking permission to redistribute their published lists commercially with attribution.
   This single step turns NSQ batches, approvals, SEC decisions and the brand registry into sellable data, which
   is DrugDen's core. Do the same for PMBI and the state corporations. Record replies in `PERMISSIONS` in
   `licensing.py`.
2. **Rebuild a sellable catalog** from permitted sources only: CDCI (brand, generic, supplier, dose form; CC BY,
   India), manufacturers' price lists (MRP, PTR, PTS, pack), NPPA Gazette prices, and the openly licensed Kaggle sets
   (CC0 / MIT / Apache; CC BY-SA only if share-alike is acceptable). Keep the current catalog for the internal
   terminal.
3. **Keep NSE and WHO data out of the API.** License NSE data later if market data becomes a product; ask WHO only
   if their lists become important.
4. **Credit every row.** The API should return each table's attribution (`licensing.attribution(table)`) with the
   data, and the Hugging Face card should list them.
5. **Legal review** of this map, especially the Gazette reading, the Form V position and CC BY-SA share-alike.
