# Molecule hygiene report

Built 2026-11-03 (commit `6c66e4d`), deployed and run on the live server. Additive and reversible like Phase 1:
`molecule_aliases` is a new table; `molecules` and `product_molecules` are untouched, and dropping the table (or
emptying it) restores the previous behaviour on the next linker run.

## What it does

Each catalog molecule node that is really another molecule is linked to a canonical one (the member with the most
products). Every set-based linker from Phase 1 (US & EU status, bans, events, launch signals) and the molecule
resolver now use canonical ids. The canonical molecule's page lists its aliases' NSQ, approval, SEC, trial, news,
tender and global records, and shows the names folded into it. An alias page keeps its own records and points to the
canonical molecule.

| Rule (applied automatically) | Example | Aliases |
|---|---|---:|
| form / route / strength words | "Clotrimazole Topical", "Miconazole Nitrate" | 259 |
| company text glued onto the name | "Cardiwin Life Caremetformin" | 79 |
| today's normaliser re-keys the name | "Ceuticals Ltdrituximab" | 67 |
| curated BAN/INN synonyms | Lignocaine = Lidocaine, Torsemide = Torasemide | 32 |
| acid / anion forms | Clavulanate → Clavulanic Acid | 16 |
| shared ChEMBL id, two synonyms in one name | Paracetamol Acetaminophen | (overlapping) |

**401 of 5,006 molecule nodes folded (8.0%); 4,605 distinct molecules remain.** 505 candidates await review
(425 near-spellings such as "Cholecalceferol", 123 glued names without company-like text, 6 ambiguous bare names
such as "Fluticasone", 2 with a chirality prefix).

Guards (learnt from the samples; each was a false merge before the guard existed):
- Different ester or salt words never merge automatically ("Fluticasone Furoate" ≠ "Fluticasone Propionate"), also
  not through a chain via a bare name.
- A bare name that fits two esters waits for review ("Fluticasone").
- Chirality prefixes are kept ("S Amlodipine" ≠ "Amlodipine"), and so are single letters ("Vitamin D" ≠ "Vitamin A").
- Mineral salts are not folded into the bare element ("Zinc Chloride" ≠ "Zinc").
- Typos are never applied without review: identity merges move quality records, so they need a person's yes.

## Before → after (live)

| Measure | Before | After |
|---|---:|---:|
| molecule nodes folded into a canonical | 0 | 401 (8.0%) |
| active product → US Orange Book (exact ingredient set) | 39.6% | 41.9% (+12,341 SKUs) |
| active product → live US patent / exclusivity | 20.0% | 20.5% |
| active product → EMA | 11.0% | 11.1% |
| banned FDC → combination | 31.7% | 33.2% |
| event → ingredient set | 10.7% | 10.8% |
| P2 SEC path, end to end | 2.5% | 2.6% |
| P5 patent path, end to end | 30.7% | 31.8% |
| P1, P3, P4 | unchanged | unchanged (blocked by maker / plant, not by molecules) |

Per-molecule counts (e.g. "molecules with a dated launch") fall slightly because folded aliases no longer count as
separate molecules; their signals now sit on the canonical molecule.

## How to review

1. Open `docs/molecule-aliases-review.csv` (all 1,011 candidate rows; `applied = False` are the pending ones,
   applied rows are listed so any can be vetoed). Regenerate it with `py -3 analysis/alias_review.py <db>`.
2. Copy decisions into `backend/pharmalens/seed/molecule_aliases.csv`: `alias_id,canonical_id,decision,note` with
   `accept` or `reject`.
3. Commit and deploy; the next `entity_linker` run (daily 05:10, or via the Feeds screen) applies them. Accepted
   pairs are stored as method `reviewed` at confidence 1.0; rejected pairs are removed even if a rule matched.

Spot-check sample: `docs/link-samples/molecule-hygiene.md`.

## Remaining risks

- Canonical names are chosen by product count, so a canonical can carry an untidy catalog name ("Pyridoxal 5").
- Plant extracts fold onto their extract name ("Liquorice" → "Liquorice Extract"), which is right for this catalog
  but loses the herb vs. extract distinction.
- Salts of one active moiety fold together ("Thiamine Nitrate" → "Thiamine Hydrochloride"); pharmacologically the
  same vitamin, but not the same salt.

## Next

Review the 505 pending candidates (the near-spellings are the bulk and mostly real). After that, the next step is the
maker / plant entity (stage 1): it is what P1 and P3 are blocked on.
