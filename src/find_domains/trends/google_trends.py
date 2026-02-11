from __future__ import annotations

import logging
from dataclasses import dataclass

from pytrends.request import TrendReq

log = logging.getLogger(__name__)


@dataclass
class TrendItem:
    name: str
    source: str
    velocity: float  # relative measure of trend strength


def fetch_google_trends() -> list[TrendItem]:
    """Fetch today's trending searches and rising queries from Google Trends."""
    items: list[TrendItem] = []
    try:
        pytrends = TrendReq(hl="en-US")

        # Daily trending searches
        trending = pytrends.trending_searches(pn="united_states")
        for _, row in trending.iterrows():
            name = str(row.iloc[0]).strip()
            if name:
                items.append(TrendItem(name=name, source="google_trends_daily", velocity=1.0))

        # Rising queries for tech/business categories
        seed_keywords = ["startup", "app", "software", "AI tool"]
        for kw in seed_keywords:
            try:
                pytrends.build_payload([kw], timeframe="now 7-d")
                related = pytrends.related_queries()
                rising = related.get(kw, {}).get("rising")
                if rising is not None and not rising.empty:
                    for _, row in rising.head(10).iterrows():
                        query = str(row["query"]).strip()
                        value = float(row.get("value", 1))
                        items.append(TrendItem(
                            name=query,
                            source="google_trends_rising",
                            velocity=min(value / 100.0, 5.0),
                        ))
            except Exception:
                log.debug("Failed to fetch rising queries for %r", kw, exc_info=True)

    except Exception:
        log.warning("Google Trends fetch failed", exc_info=True)

    # Deduplicate by lowercased name, keeping highest velocity
    seen: dict[str, TrendItem] = {}
    for item in items:
        key = item.name.lower()
        if key not in seen or item.velocity > seen[key].velocity:
            seen[key] = item

    return list(seen.values())
