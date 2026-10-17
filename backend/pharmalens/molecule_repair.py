"""Repair molecule names damaged in the source datasets before they become catalog molecules.

Damage found in the master dataset (2026-10 audit, 1,487 of 13,432 distinct molecule strings):
* strengths parsed as molecules, from a column-mangled composition format
  ("METHYLCOBALAMIN+ PREGABALIN-750+ 75MCG+ MG" yields "75MCG" and "MG");
* doses glued onto names ("LACTULOSE-10GM", "PREGABALIN75MG", "LACTOBACILLUS-60MILLION SPORES", "HEPARIN-5000I.U");
* OCR-style character loss: a leading letter read as "0" ("0ETA ARTEETHER" = beta, "0RNITHINE", "0ODINE") or dropped
  ("YRIDOXINE", "ITAMIN B1");
* two molecules glued by that damage ("ZINC-0ARNITINE" = zinc + carnitine), unlike single compounds written the same
  way ("POVIDONE-0ODINE" = povidone-iodine, "CALCITONIN-0ALMON" = calcitonin salmon);
* synonyms in parentheses ("PARACETAMOL(ACETAMINOPHEN)", "CHOLECALCIFEROL(VIT D3)").

A repair is accepted only when it yields words or names that occur undamaged elsewhere in the same data;
unrecoverable fragments are dropped rather than guessed.
"""
import re
from collections import Counter

from .normalize import norm

UNIT_WORD = (r"(?:mcg|µg|ug|mg|gm|g|ml|iu|i\s?u|kiu|miu|au|lf|units?|elisa\s+units?|lac\s+units?|"
             r"mill+ions?|billions?|mn|bn|lac|lakh|cfu|pfu|ffu|fcc|f\s?u|galu|ccid\d*|hut|ppmw?|cst|cells?|s?pores?|m|k)")
UNIT = rf"{UNIT_WORD}(?:\s*{UNIT_WORD})*(?:\s+w(?:\s+[wv])?)?"
PURE_DOSE = re.compile(rf"^[\d\s.]*\s*(?:{UNIT})?$")
# a dose starts at a word boundary ("vit d3 60kiu" keeps "d3"); several numbers may precede the unit ("1 4gm")
TRAILING_DOSE = re.compile(rf"(?:^|\s)\d[\d.]*(?:\s+\d[\d.]*)*\s*{UNIT}\b.*$")
GLUED_DOSE = re.compile(rf"(?<=[a-z])\d[\d.]*\s*{UNIT}\b.*$")
# vitamin codes glued to a dose: "vitamin d31000iu" -> "vitamin d3", "vitamin b61 5mg" -> "vitamin b6"
VITAMIN_GLUED = re.compile(rf"\b(vit(?:amin)?\s+(?:b12|b1|b2|b3|b5|b6|b7|b9|d2|d3|k1|k2|e|c|a))\d[\d.\s]*{UNIT}\b.*$")
# release descriptors ("Cephalexin Extended Release", "Metformin Hydrochloride SR") describe the product, not the molecule
RELEASE = re.compile(r"\b(?:extended|sustained|controlled|modified|delayed|prolonged|immediate)\s+release\b|\s(?:sr|er|xr|cr|mr|pr|dr)$")
FORM_ONLY = {"tablet", "tablets", "capsule", "capsules", "powder", "powder supplement", "injection", "syrup", "suspension",
             "device", "light", "drops", "cream", "gel", "ointment", "solution", "sachet", "kit", "mg", "mcg", "gm", "ml",
             "unit", "units", "vitamin", "vitamins"}
MIN_FIXED_LEN = 5
# parenthesised words that qualify the substance rather than name a synonym
QUALIFIERS = {"human", "rdna", "recombinant", "live attenuated", "inactivated", "bovine", "porcine", "equine", "natural",
              "natural micronized", "micronized", "liposomal", "pegylated", "freeze dried", "lyophilized"}
# fragments whose repair is ambiguous by spelling alone; reviewed against the products that carry them
OCR_FIXED = {"0eta": "beta", "0cetyl": "acetyl", "0nzyme": "coenzyme"}
# leading letter lost; fixed only from this reviewed list (a general rule would also turn "ethyl" into "methyl")
LOST_LETTER = {"yridoxine": "pyridoxine", "itamin": "vitamin", "yridoxal": "pyridoxal", "olic": "folic", "ethylcobalamin": "methylcobalamin"}


class MoleculeRepair:
    def __init__(self, raw_names):
        vocab, names = Counter(), Counter()
        for n in raw_names:
            s = norm(re.sub(r"\(.*?\)", " ", n or ""))
            # undamaged names only: no OCR "0x" fragments and no dose (digits inside names such as "vitamin d3" are fine)
            if not s or re.search(r"(^|\s)\d*0[a-z]", s) or PURE_DOSE.fullmatch(s) or TRAILING_DOSE.search(s) or GLUED_DOSE.search(s):
                continue
            names[s] += 1
            for t in s.split():
                if t.isalpha() and len(t) >= 3:
                    vocab[t] += 1
        self.vocab, self.names = vocab, names
        self.stats = Counter()

    def _fix_token(self, t: str) -> str | None:
        """Return the repaired token, the token unchanged, or None to drop it."""
        z = re.fullmatch(r"\d*(0[a-z]+)", t)
        if z and z.group(1) in OCR_FIXED:
            self.stats["ocr_zero"] += 1
            return OCR_FIXED[z.group(1)]
        m = re.fullmatch(r"\d*0([a-z]+)", t)          # "0rnithine", "100rnithine", "0adenosyl"
        if m:
            rest = m.group(1)
            # the 0 replaced a letter ("0rnithine") or was inserted ("0adenosyl")
            cands = sorted(({c + rest for c in "abcdefghijklmnopqrstuvwxyz"} | {rest}), key=lambda w: -self.vocab.get(w, 0))
            cands = [w for w in cands if self.vocab.get(w, 0) >= 3 and len(w) >= MIN_FIXED_LEN - 1]
            if len(rest) + 1 >= MIN_FIXED_LEN and cands and (
                    len(cands) == 1 or self.vocab[cands[0]] >= 5 * self.vocab[cands[1]]):
                self.stats["ocr_zero"] += 1
                return cands[0]
            self.stats["ocr_dropped"] += 1
            return None
        m = re.fullmatch(r"\d*1([a-z]{4,})", t)       # "1odochlorhydroxyquin", "10odine"
        if m and self.vocab.get("i" + m.group(1).lstrip("0")):
            self.stats["ocr_one"] += 1
            return "i" + m.group(1).lstrip("0")
        if t in LOST_LETTER:
            self.stats["lost_letter"] += 1
            return LOST_LETTER[t]
        return t

    def _clean(self, s: str) -> str | None:
        s = norm(s)
        s = re.sub(r"\bv itamin\b", "vitamin", s)
        if not s or s in FORM_ONLY or PURE_DOSE.fullmatch(s):
            return None
        s = RELEASE.sub(" ", s).strip()
        s2 = VITAMIN_GLUED.sub(r"\1", s)
        s2 = GLUED_DOSE.sub("", s2) if s2 == s else s2
        s2 = TRAILING_DOSE.sub("", s2).strip()
        s2 = re.sub(r"\s+(?:mcg|mg|gm|ml|iu|i u|units?)$", "", s2).strip()   # bare unit left behind ("cyanocobalamin mcg")
        if s2 != s:
            self.stats["dose_stripped"] += 1
            s = s2
        toks = [f for f in (self._fix_token(t) for t in s.split()) if f]
        s = " ".join(toks).strip()
        return None if len(s) < 3 or s in FORM_ONLY else s

    def repair(self, name: str | None) -> list[str]:
        """Clean molecule names for one raw string: usually one, none when unrecoverable, two when glued."""
        raw = name or ""
        if not raw.strip():
            return []
        # synonym in parentheses: keep the name outside them ("Paracetamol(Acetaminophen) 1Gm" -> "Paracetamol 1Gm");
        # qualifiers stay ("Insulin (Human)"), and so do parentheses inside a chemical name ("4(methylthio)butyrate")
        def paren(m):
            inner = norm(m.group(1))
            if inner in QUALIFIERS:
                return f" {inner} "
            return " "
        outside = re.sub(r"(?<!\d)\(([^)]*)\)?", paren, raw)
        if len(norm(outside)) >= 3 and norm(outside) != norm(raw):
            self.stats["synonym_dropped"] += 1
            raw = outside
        # "Zinc-0Arnitine": a hyphen followed by OCR damage can join two molecules
        parts = re.split(r"-(?=\d*0[a-z])", raw, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            left, right = self._clean(parts[0]), self._clean("0" + parts[1].lstrip("0123456789") if not parts[1].startswith("0") else parts[1])
            joined = self._clean(raw)
            known = lambda x: self.names.get(x) or self.names.get("l " + x)   # "carnitine" is usually written "l carnitine"
            if left and right and not self.names.get(joined or "") and known(left) and known(right):
                self.stats["split_glued"] += 1
                return [left, right]
            return [joined] if joined else []
        s = self._clean(raw)
        if s is None:
            self.stats["dropped"] += 1
            return []
        return [s]
