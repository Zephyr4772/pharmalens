# NSQ batch → SKU (#7) report

Built 2026-11-03 (commit `ace7175`), deployed and run on the live server. Additive: links in `entity_links`
(linker `nsq:product`); `reg_nsq` is unchanged.

## What it does

A failed (NSQ) or spurious batch is matched to the catalog SKU it is, and through that SKU to its marketer and group.
This lets a contract manufacturer's failed batch reach the brand owner, which the maker entity alone could not do.

| Evidence tier | Confidence | Batches |
|---|---:|---:|
| brand named in the batch + agreeing ingredients + manufacturer related to the SKU (marketer itself, registered the brand under 84AB, or makes for that marketer) | 0.95 | 257 |
| spurious batch bearing a SKU's brand (counterfeit of that SKU) | 0.85 | (in the above set when present) |
| no brand, but exactly one SKU by a related manufacturer with the same complete ingredients, strength and form | 0.85 | 197 |
| brand + ingredients but an unrelated manufacturer; brand without a stated strength across variants; several candidate SKUs; a named brand missing from the catalog | 0.6–0.7, inferred | 1,309 batches |

Guards added after reading the samples (each fixed real false matches):
- ingredients are resolved with the brand words removed, so "Glimicut-1" (glimepiride) cannot match "Glimicut M2";
- a number in the brand is its strength and must equal the SKU's first number ("Rosuvas 10" ≠ "Rosuvas 20mg … 10's");
- a variant word on the SKU (MCT, Rapid, SR, Forte, Plus…) must appear in the batch text ("Telma H" ≠ "Telma-MCT",
  "Okamet 500" ≠ "Okamet 500 SR");
- if the batch names a brand the catalog lacks, another brand by the same maker is never chosen at high confidence.

## Results (live)

| Measure | Before | After |
|---|---:|---:|
| NSQ batch → SKU (high) | 0 | 454 (4.5%) |
| NSQ batch since 2025 → SKU (high) | 0 | 184 (3.9%) |
| NSQ batch → listed group via its SKU's marketer | 0 | 88 |
| P1 via the SKU: SKU → group → ticker → price → news, all hops | 0 | 5 (0.1%) |
| P1 as originally defined (via the batch's manufacturer) | 1.0% | 1.0% |

Pages: product pages show "Quality record of this SKU"; company pages and the group Risk tab show "Failed batches of
this marketer's / group's SKUs", including contract-made ones.

## Why coverage is low: the ceiling

Of the 4,770 batches listed since January 2025:

| | Batches |
|---|---:|
| unbranded generic, manufacturer not in the catalog (government-supply lots) | 1,732 |
| unbranded generic, manufacturer in the catalog but no SKU with that exact ingredients + strength + form | 1,488 |
| branded, but the brand is not in the catalog (e.g. Abazolid, Calxia, Leaftel) | 874 |
| inferred candidates only | 492 |
| linked at high confidence | 184 |

76% of batches carry no brand, and most named brands are small labels the catalog does not list. A fuller SKU list,
like the sellable catalog rebuild from CDCI's 93k brands, would raise the ceiling more than any matcher change.
Listed groups' own SKUs rarely fail, so P1's ticker hop stays small by nature.

## Risks

- A batch with a brand but no strength can match several pack sizes of one strength; those are linked together (the
  claim "this brand and strength failed" holds for each).
- "Counterfeit of" relies on the CDSCO category SPURIOUS; spurious products not yet labelled as such appear as
  inferred "brand, different maker".
- Variant words outside the list (e.g. "Kid", "LS") can still slip through; the sample (`docs/link-samples/07-nsq-sku.md`)
  showed none at high confidence.

## Next

- **Plant sites (stage 2):** approval site addresses, NSQ manufacturer addresses and US FDA FEI numbers. This is what
  P3 is blocked on.
- **CDCI brands as catalog SKUs:** 93k brands with structured ingredients and suppliers. They would lift NSQ → SKU and
  the contract map, and they are the sellable catalog's spine.
