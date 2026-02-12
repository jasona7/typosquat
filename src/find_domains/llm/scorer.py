from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import OpenAI

from find_domains.checker.availability import AvailabilityResult
from find_domains.config import ScoringConfig
from find_domains.llm.client import chat_json

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a domain investment analyst. Score domain opportunities based on commercial value \
and risk.

For each domain, assess:
1. **Estimated CPC** ($): What advertisers pay for clicks on the original brand's keywords
2. **Commercial niche**: The industry/niche (e.g., "AI SaaS", "fintech", "e-commerce")
3. **UDRP risk** (1-10): How likely the brand owner files a UDRP complaint
   - 1-3: Small startup, unlikely to pursue
   - 4-6: Medium company, might pursue
   - 7-10: Large corp with active legal team

Return JSON:
{
  "assessments": [
    {
      "brand": "BrandName",
      "estimated_cpc": 2.50,
      "commercial_niche": "AI SaaS",
      "udrp_risk": 4,
      "reasoning": "Brief explanation"
    }
  ]
}\
"""


@dataclass
class ScoredDomain:
    domain: str
    original: str
    tld: str
    typo_type: str
    score: float
    breakdown: dict[str, float]


def _tld_quality_score(tld: str) -> float:
    """Score TLD quality on 0-1 scale."""
    tld_scores = {
        ".com": 1.0, ".net": 0.7, ".org": 0.65,
        ".io": 0.8, ".ai": 0.85, ".co": 0.75,
        ".app": 0.6, ".dev": 0.55, ".xyz": 0.3,
        ".me": 0.4, ".gg": 0.45, ".tv": 0.4,
    }
    return tld_scores.get(tld, 0.3)


def _domain_length_score(domain: str) -> float:
    """Shorter domains score higher."""
    name = domain.split(".")[0]
    length = len(name)
    if length <= 5:
        return 1.0
    elif length <= 8:
        return 0.8
    elif length <= 12:
        return 0.6
    elif length <= 16:
        return 0.4
    return 0.2


def score_domains(
    client: OpenAI | None,
    model: str,
    available: list[AvailabilityResult],
    trend_velocities: dict[str, float],
    scoring: ScoringConfig,
    skip_llm: bool = False,
) -> list[ScoredDomain]:
    """Score available domains on a 0-100 scale."""
    if not available:
        return []

    # Get LLM assessments for commercial value and risk
    assessments: dict[str, dict] = {}
    if client and not skip_llm:
        unique_brands = list({r.candidate.original for r in available})
        brands_text = ", ".join(unique_brands)

        result = chat_json(
            client, model, SYSTEM_PROMPT,
            f"Assess the following brands for domain investment: {brands_text}",
        )
        for a in result.get("assessments", []) if isinstance(result, dict) else []:
            brand = a.get("brand", "").lower()
            assessments[brand] = a

    scored: list[ScoredDomain] = []

    for result in available:
        c = result.candidate
        brand_lower = c.original.lower()

        # 1. Trend Velocity (0-25)
        velocity = trend_velocities.get(brand_lower, 0.5)
        trend_score = min(velocity / 3.0, 1.0) * scoring.trend_velocity_weight

        # 2. Commercial Value (0-25)
        llm_data = assessments.get(brand_lower, {})
        cpc = llm_data.get("estimated_cpc", 1.0)
        commercial_score = min(cpc / 10.0, 1.0) * scoring.commercial_value_weight

        # 3. Typo Plausibility (0-20)
        plausibility_score = c.confidence * scoring.typo_plausibility_weight

        # 4. Domain Quality (0-15)
        tld_q = _tld_quality_score(c.tld)
        len_q = _domain_length_score(c.domain)
        quality_score = ((tld_q + len_q) / 2.0) * scoring.domain_quality_weight

        # 5. Risk Penalty (0 to -15)
        udrp_risk = llm_data.get("udrp_risk", 3)
        risk_penalty = (udrp_risk / 10.0) ** 1.5 * scoring.risk_penalty_max

        total = trend_score + commercial_score + plausibility_score + quality_score - risk_penalty
        total = max(0.0, min(100.0, total))

        scored.append(ScoredDomain(
            domain=c.domain,
            original=c.original,
            tld=c.tld,
            typo_type=c.typo_type,
            score=round(total, 1),
            breakdown={
                "trend_velocity": round(trend_score, 1),
                "commercial_value": round(commercial_score, 1),
                "typo_plausibility": round(plausibility_score, 1),
                "domain_quality": round(quality_score, 1),
                "risk_penalty": round(-risk_penalty, 1),
            },
        ))

    scored.sort(key=lambda d: d.score, reverse=True)
    return scored
