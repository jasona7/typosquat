from __future__ import annotations

import logging
import re

import httpx

from find_domains.trends.google_trends import TrendItem

log = logging.getLogger(__name__)

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

# Words unlikely to be brand names
STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "how", "why", "what",
    "show", "ask", "tell", "new", "from", "with", "for", "and", "not",
    "can", "will", "has", "have", "had", "this", "that", "your", "our",
    "my", "its", "all", "any", "but", "into", "about", "just", "than",
    "now", "get", "got", "use", "way", "who", "hn", "yc",
})

# Pattern to extract likely brand/product names: capitalized words or known patterns
BRAND_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\.[a-z]+)*\b")


def _extract_brands(title: str) -> list[str]:
    """Extract potential brand/product names from a HN title."""
    # Find capitalized words that could be brand names
    matches = BRAND_PATTERN.findall(title)
    # Also look for all-caps short words (acronyms like "AI", "GPT")
    acronyms = re.findall(r"\b[A-Z]{2,6}\b", title)

    candidates = []
    for m in matches + acronyms:
        cleaned = m.strip().lower()
        if cleaned not in STOP_WORDS and len(cleaned) >= 3:
            candidates.append(m.strip())

    return candidates


def fetch_hackernews(max_stories: int = 60) -> list[TrendItem]:
    """Fetch top HN stories and extract brand/product names."""
    items: list[TrendItem] = []

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(HN_TOP_URL)
            resp.raise_for_status()
            story_ids = resp.json()[:max_stories]

            for story_id in story_ids:
                try:
                    r = client.get(HN_ITEM_URL.format(story_id))
                    r.raise_for_status()
                    story = r.json()
                    title = story.get("title", "")
                    score = story.get("score", 0)

                    brands = _extract_brands(title)
                    for brand in brands:
                        velocity = min(score / 200.0, 3.0)
                        items.append(TrendItem(
                            name=brand,
                            source="hackernews",
                            velocity=velocity,
                        ))
                except Exception:
                    log.debug("Failed to fetch HN story %s", story_id, exc_info=True)

    except Exception:
        log.warning("Hacker News fetch failed", exc_info=True)

    # Deduplicate
    seen: dict[str, TrendItem] = {}
    for item in items:
        key = item.name.lower()
        if key not in seen or item.velocity > seen[key].velocity:
            seen[key] = item

    return list(seen.values())
