# Maker entity (plant stage 1) report

Built 2026-11-03 (commits `d656d8f` and `6c9fb78`), deployed and run on the live server. Additive like
Phase 1: new tables `makers` and `maker_makes_for`, new links in `entity_links` (linkers `maker:*`); no source
table changed.

## A correction to the audit

The audit treated `products.manufacturer_raw` as contract-maker data. It is not: on 97% of SKUs it is the marketer's
own name, because the catalog built its company list from that field. Maker evidence lives elsewhere, and that is what
stage 1 uses:

| Source | Role | Records linked to a maker |
|---|---|---:|
| `reg_nsq.manufacturer` | manufacturer of the failed batch (label) | 8,913 of 10,019 (89.0%) |
| `brand_registry.firm_name` | licensed manufacturer that registered the brand (Rule 84AB) | 89,166 of 90,464 (98.6%) |
| `usfda_actions.firm` | firm in a US FDA recall or import alert | 264 of 272 Indian (97.1%) |
| `reg_approvals.applicant` | CDSCO permission holder (may be an importer) | 3,710 |
| `cdci_supplier.supplier_name` | CDCI supplier | 8,121 |
| `procurement_rates.supplier` | state tender supplier | 5,776 |
| `firm_debarments.firm` | debarred firm | 42 |

## What was built

- **Makers**: 10,821 firms keyed by strict firm key (address and plant text cut; "(a unit / division of X)" removed
  from the key and resolved to X separately). 10,565 have a distinctive name (links 0.9); 256 are generic-word names
  like "S P Pharma" that several firms may share (links 0.7, inferred, badge on the page).
- **Maker → company / group**: 70.7% of makers are a catalog company (equal firm key, or the "a unit of" matcher), and
  71.3% reach a curated group or an auto-group through it; curated group name patterns cover the rest where they match.
- **Contract-manufacturing map**: an 84AB brand registration links to the catalog SKUs whose name starts with the brand
  and whose canonical ingredient set equals the registration's complete set (0.85 when two brand words match, 0.7 when
  one). Brands that are just a generic name ("Amlodipine 5") are excluded, and registrations matching SKUs of several
  marketers stay inferred. Result: 9,420 active SKUs with a registered manufacturer and 847 maker → marketer pairs:
  117 own, 27 same group (e.g. Sun Pharma Laboratories → Sun Pharmaceutical), **703 contract** (e.g. The Madras
  Pharmaceuticals → USV and Lupin, Unichem → Torrent, Medispray → Cipla).
- **Pages**: `/mk/<key>` maker profile (records by role, who it makes for, catalog company and group); "Made by" on
  company pages (own / same group / contract makers); "Registered manufacturer" on product pages; NSQ manufacturers on
  molecule pages link to their maker.

## Paths (live)

| Path | Hop | Before | After |
|---|---|---:|---:|
| P3 US FDA (Indian actions, n = 272) | action → maker | 0 | 264 |
| | maker → any group (curated or auto) | 0 | 120 |
| | curated group (incl. via maker) | 49 | 51 |
| | plant | 0 | 0 (stage 2) |
| P1 NSQ (since 2025, n = 4,770) | curated group via maker | 220 | 235 |
| | end to end | 1.0% | 1.0% |

End-to-end completion for P1 and P3 does not move yet: P1 still needs the batch → SKU hop, and P3 needs plant sites.
What stage 1 adds is the firm in between: every NSQ batch, US FDA action, brand registration, tender and debarment of
a firm is now reachable from one page, and from its company and group.

## Risks

- A maker is a legal firm; its plants are merged (stage 2 separates sites by address).
- Generic-word firm names (256) may merge several small firms: inferred, flagged on the page.
- The contract map only covers brands registered under 84AB that match a catalog SKU (8.6% of registrations); the
  registry is dominated by smaller firms, so large marketers' own manufacturing is under-represented.
- Approval applicants are often importers or marketers, not manufacturers; the role is shown on every link.
- The server runs DuckDB 2.0.0 and this machine 1.5.5; the maker linker failed live once on a stricter rule (an
  unread result) and was fixed. Local tests do not catch such differences: worth pinning the same version in both.

## Next

**NSQ batch → SKU** (roadmap #7) is now feasible and is what P1 is blocked on: the batch's maker, its brand (often in
the product text, e.g. "(CLAVAM 625)") matched to that maker's 84AB registrations, and the exact ingredient set give
the SKU and its marketer, so a contract manufacturer's failed batch reaches the listed group that sells it. After that,
plant sites (stage 2) from approval site addresses, NSQ addresses and US FDA FEI numbers.
