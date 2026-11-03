# Plant sites (stage 2) report

Built 2026-11-03 (commit `bb6706e`), deployed and run on the live server. Additive: new table `sites`, links in
`entity_links` (linker `site:records`); no source table changed.

## What a site is

One firm (maker) at one place: in India its **PIN code**, abroad its country and postal code. Units of one firm
that share a PIN are one site; their unit labels ("Unit II") are kept on the site. Sites inherit the maker's catalog
company and its curated group or auto-group.

| Source | Address used | Records → site |
|---|---|---:|
| CDSCO approvals (`sites` list) | each named manufacturing site | 3,615 of 3,714 approvals (97.3%) |
| NSQ / spurious batches | manufacturer address on the label | 8,810 of 10,019 (87.9%) |
| US FDA actions (Indian) | import-alert address, recall city | 152 of 289 (52.6%) |
| UP debarments | firm address | 42 |

How a record reaches its site:
- **PIN in the address (0.9).** The site is defined by the record's own address.
- **No PIN, but the firm's single PIN site shares the record's locality words (0.85, `locality_match`).** For
  example, Mylan's FDF-3 import alert → its Pithampur site; Centrient's Toansa alert → PIN 144533.
- **Otherwise, a district-level site of that firm (0.85, `district_site`).** For example, "Kadi, Gujarat" → that
  firm's plant in Kadi.
- **Abroad without a postal code: no site.**

Result: **4,363 sites** (3,074 by PIN, 810 foreign, 478 district-level); 464 of them belong to a curated group.

Guards from the samples:
- Placeholder firm names ("Other Site, …") are skipped.
- Role prefixes are stripped ("Supplied by …", "Mfd. by …"). This also fixed the maker entity.
- Foreign firm names are cut at their legal suffix (GmbH, AG, S.A., LLC…), so product text glued after the name
  doesn't create a new firm.
- An Indian state plus a PIN overrides a wrong country in the source ("Punjab … Iran-144533").

## Paths (live)

| Path | Before | After |
|---|---:|---:|
| P3 US FDA action → **plant** | 0 | 152 |
| P3 end to end (plant + curated group + ticker + US applications) | 0% | **8.3%** (24 of 289) |

The remaining P3 gap is two different things:
1. **No site:** actions whose address has no PIN, district or locality match (mostly recalls without a city).
2. **No listed group:** actions by firms outside any listed group, which is most Indian import alerts (small API and
   cosmetics firms).

## Pages

- `/st/<key>`: site profile with address, firm, company and group; approvals naming the site, failed batches,
  US FDA actions and debarments there; the firm's other sites.
- **Sites** on maker pages.
- **Plants** on the group Risk tab: every plant of the group's makers with approvals, NSQ, US FDA and debarment
  counts. For example, Sun's 30 plants, with Halol (PIN 389350) showing 16 approvals and its US FDA action.

## Risks

- A firm's units sharing a PIN are merged; units in different PINs are separate (that's usually right).
- District sites are coarser than PIN sites: a firm with two plants in one district has one district site.
- Locality matching needs a shared distinctive locality word; a record naming only a city a firm has several
  plants in is not matched to any of them (it gets a district site instead).
- No US FDA FEI numbers yet. The FDA Data Dashboard (inspections and 483s by FEI) would give exact site identity
  and inspection outcomes; it needs an API account.

## Next

- **US FDA inspections by FEI** (Data Dashboard): inspection dates and classifications per site, matched to these
  sites by firm + address. This is the strongest remaining investor signal.
- **CDCI brands as catalog SKUs**: lifts NSQ → SKU and the contract map.
