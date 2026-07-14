"""Shared helpers for the memory subsystem.

Fact-ID allocation, content dedup, and keyword extraction were previously
implemented independently (with drift) across memory.py, data_management.py,
context_retrieval.py, and conversation_memory.py. This module is the single
source of truth for all of them.
"""

import re
from typing import Dict, List, Optional

STOPWORDS = frozenset({
    'a', 'an', 'the', 'and', 'or', 'but', 'if', 'then', 'else', 'when',
    'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into',
    'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from',
    'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again',
    'further', 'once', 'here', 'there', 'all', 'any', 'both', 'each',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'own', 'same', 'so', 'than', 'too', 'very', 'can', 'will',
    'just', 'should', 'now', 'is', 'am', 'are', 'was', 'were', 'be',
    'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'doing',
    'would', 'could', 'may', 'might', 'must', 'shall', 'of', 'it', 'its',
    'this', 'that', 'these', 'those', 'i', 'me', 'my', 'we', 'our', 'you',
    'your', 'he', 'him', 'his', 'she', 'her', 'they', 'them', 'their',
    'what', 'which', 'who', 'whom', 'how', 'why', 'where', 'user', 'likes',
    'wants', 'uses', 'prefers'
})


def extract_keywords(text: str) -> set:
    """Lowercase content words of a text, minus stopwords and short tokens."""
    words = re.findall(r'[a-z0-9]+', text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def normalize_content(content: str) -> str:
    """Normal form used for duplicate detection."""
    return ' '.join(content.lower().split())


def find_duplicate(content: str, facts: List[Dict]) -> Optional[Dict]:
    """Return the existing fact whose content matches `content`, if any."""
    normalized = normalize_content(content)
    for fact in facts:
        if normalize_content(fact.get("content", "")) == normalized:
            return fact
    return None


def max_id_number(items: List[Dict], prefix: str) -> int:
    """Highest numeric suffix among ids like '<prefix>_NNN' (0 if none)."""
    highest = 0
    for item in items:
        item_id = item.get("id", "")
        if item_id.startswith(f"{prefix}_"):
            try:
                highest = max(highest, int(item_id.split("_")[1]))
            except (ValueError, IndexError):
                pass
    return highest
