"""
Text similarity helpers using RapidFuzz.
Centralises all fuzzy-matching logic so the planner stays clean.
"""

from __future__ import annotations

from rapidfuzz import fuzz, process

import config
from utils.logger import get_logger

log = get_logger(__name__)


def best_match(
    query: str,
    candidates: list[str],
    threshold: float | None = None,
) -> tuple[str, float] | None:
    """
    Find the best fuzzy match for *query* among *candidates*.

    Uses token_set_ratio which handles word-order variation and partial overlap.

    Args:
        query:      The string to look up (e.g. goal keyword or target_text).
        candidates: List of strings to search (e.g. visible_texts).
        threshold:  Minimum score (0–100) to consider a match.
                    Defaults to config.FUZZY_MATCH_THRESHOLD.

    Returns:
        (matched_string, score) if a match exceeds the threshold, else None.
    """
    thr = threshold if threshold is not None else config.FUZZY_MATCH_THRESHOLD

    if not candidates or not query:
        return None

    result = process.extractOne(
        query,
        candidates,
        scorer=fuzz.token_set_ratio,
    )

    if result is None:
        return None

    match_text, score, _ = result
    log.debug("Fuzzy '%s' → '%s' (score=%.1f)", query, match_text, score)

    if score >= thr:
        return match_text, score
    return None


def all_matches(
    query: str,
    candidates: list[str],
    threshold: float | None = None,
    limit: int = 5,
) -> list[tuple[str, float]]:
    """
    Return up to *limit* matches above *threshold*, ranked by score.

    Args:
        query:      Search string.
        candidates: Candidate strings.
        threshold:  Minimum match score (default: config.FUZZY_MATCH_THRESHOLD).
        limit:      Maximum number of results to return.

    Returns:
        List of (matched_string, score) tuples, best-first.
    """
    thr = threshold if threshold is not None else config.FUZZY_MATCH_THRESHOLD

    if not candidates or not query:
        return []

    raw = process.extract(
        query,
        candidates,
        scorer=fuzz.token_set_ratio,
        limit=limit,
    )

    return [(text, score) for text, score, _ in raw if score >= thr]


def similarity_score(a: str, b: str) -> float:
    """
    Compute a simple similarity score between two strings.

    Args:
        a: First string.
        b: Second string.

    Returns:
        Score in [0.0, 100.0].
    """
    return float(fuzz.token_set_ratio(a, b))
