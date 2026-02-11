from __future__ import annotations

import logging

from openai import OpenAI

from find_domains.llm.client import chat_json
from find_domains.trends.google_trends import TrendItem

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a domain investment analyst. Your job is to identify trending brand/product \
names that would make good typosquatting domain targets.

Evaluate each trend item and select the best targets based on:
1. The name is hard to spell (unusual spelling, foreign words, made-up terms)
2. High commercial intent (people searching to buy/use the product)
3. Growing rapidly (high trend velocity)
4. Unlikely to aggressively pursue UDRP (avoid Fortune 500 companies with large legal teams)
5. The brand is digital/online-focused (more valuable for domain traffic)

Return your response as JSON with this structure:
{
  "targets": [
    {
      "name": "BrandName",
      "reasoning": "Brief explanation of why this is a good target",
      "difficulty_to_spell": 8,
      "commercial_intent": 7,
      "udrp_risk": 3
    }
  ]
}

Select up to the requested number of targets. Rank them by overall opportunity quality.\
"""


def filter_trends(
    client: OpenAI,
    model: str,
    trends: list[TrendItem],
    max_targets: int = 50,
) -> list[dict]:
    """Use LLM to filter and rank trending brands for typosquat targeting.

    Returns list of dicts with 'name', 'reasoning', and scoring fields.
    """
    if not trends:
        return []

    trend_text = "\n".join(
        f"- {t.name} (source: {t.source}, velocity: {t.velocity:.1f})"
        for t in trends
    )

    user_prompt = f"""\
Here are the current trending brands/products/terms:

{trend_text}

Select the top {max_targets} best typosquatting targets from this list. \
Focus on names that are genuinely hard to spell and have high commercial value.\
"""

    result = chat_json(client, model, SYSTEM_PROMPT, user_prompt)

    targets = result.get("targets", []) if isinstance(result, dict) else []

    log.info("LLM trend filter selected %d targets from %d trends", len(targets), len(trends))
    return targets[:max_targets]
