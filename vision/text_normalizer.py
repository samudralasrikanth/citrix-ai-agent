"""
╔══════════════════════════════════════════════════════════════════╗
║  Text Normalizer — OCR Correction Layer                         ║
║  Corrects the most common PaddleOCR misreadings before          ║
║  fuzzy matching, especially for short button labels.            ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
    from vision.text_normalizer import normalize, normalized_pairs

Examples:
    normalize("0K")     → "ok"
    normalize(" Ok ")   → "ok"
    normalize("Ye5")    → "yes"
    normalize("CANCEl") → "cancel"
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

# ── OCR confusion map (applied left-to-right, order matters) ─────────────────
# These are the most frequent PaddleOCR errors on Citrix/Windows UI text.
_CONFUSION_MAP: List[Tuple[str, str]] = [
    # Digit → letter lookalikes
    ("0", "o"),
    ("1", "l"),
    ("5", "s"),
    ("6", "b"),   # rare but seen in small fonts
    ("8", "b"),   # rare
    # Punctuation lookalikes
    ("|", "l"),
    ("!", "l"),
    ("/", "l"),   # slanted 1 in some fonts
    ("@", "a"),
    # Multi-char clusters
    ("rn", "m"),
    ("vv", "w"),
    ("li", "h"),  # very small text
    # Common UI word fixes (applied whole-string only via dedicated table)
]

# Whole-string substitutions for specific known misreads of common UI labels
_WHOLE_WORD_FIXES: dict[str, str] = {
    "0k":      "ok",
    "0kay":    "okay",
    "ye5":     "yes",
    "n0":      "no",
    "cance1":  "cancel",
    "c1ose":   "close",
    "c10se":   "close",
    "app1y":   "apply",
    "1ogin":   "login",
    "submlt":  "submit",
    "confi rm": "confirm",
    "conhrm":  "confirm",
}


def normalize(text: str) -> str:
    """
    Normalize a raw OCR string into a clean, lowercase, de-noised form
    suitable for fuzzy matching.

    Pipeline:
        1. Unicode NFKC normalisation (converts fullwidth chars, ligatures)
        2. Strip surrounding whitespace
        3. Lowercase
        4. Collapse internal whitespace runs to single space
        5. Remove non-alphanumeric junk characters (keep spaces)
        6. Apply OCR confusion map character substitutions
        7. Apply whole-word dictionary correction for known misreads
    """
    if not text:
        return ""

    # 1. Unicode normalisation
    t = unicodedata.normalize("NFKC", text)

    # 2–3. Strip + lowercase
    t = t.strip().lower()

    # 4. Collapse whitespace
    t = re.sub(r"\s+", " ", t)

    # 5. Remove non-alphanumeric except spaces (keeps hyphens etc as spaces)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    # 6. OCR confusion map (character-level)
    for wrong, right in _CONFUSION_MAP:
        t = t.replace(wrong, right)

    # 7. Whole-word dictionary
    fixed = _WHOLE_WORD_FIXES.get(t)
    if fixed:
        t = fixed

    return t


def normalize_pair(raw: str, target: str) -> Tuple[str, str]:
    """Normalize both the OCR result and the search target."""
    return normalize(raw), normalize(target)


def normalized_pairs(
    ocr_results: list[dict],
    target: str,
) -> list[dict]:
    """
    Return a copy of *ocr_results* with a 'norm' key added,
    plus the normalized version of *target*.

    This lets the caller compare norm↔norm while still having
    the original text and box available.
    """
    norm_target = normalize(target)
    out = []
    for r in ocr_results:
        copy = dict(r)
        copy["norm"] = normalize(r.get("text", ""))
        out.append(copy)
    return out, norm_target
