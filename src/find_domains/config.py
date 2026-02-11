from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


@dataclass
class ScoringConfig:
    trend_velocity_weight: int = 25
    commercial_value_weight: int = 25
    typo_plausibility_weight: int = 20
    domain_quality_weight: int = 15
    risk_penalty_max: int = 15


@dataclass
class OpenAIConfig:
    filter_model: str = "gpt-4o-mini"
    creative_model: str = "gpt-4o"
    scorer_model: str = "gpt-4o-mini"


@dataclass
class RateLimitsConfig:
    dns_delay_ms: int = 100
    rdap_delay_ms: int = 500


@dataclass
class Config:
    tlds_tier1: list[str] = field(default_factory=lambda: [".com", ".net", ".org", ".io", ".ai", ".co"])
    tlds_tier2: list[str] = field(default_factory=lambda: [".app", ".dev", ".xyz", ".me", ".gg", ".tv"])
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    rate_limits: RateLimitsConfig = field(default_factory=RateLimitsConfig)
    max_targets: int = 50
    max_typos_per_target: int = 30

    @property
    def all_tlds(self) -> list[str]:
        return self.tlds_tier1 + self.tlds_tier2


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return Config()

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        return Config()

    tlds = raw.get("tlds", {})
    scoring_raw = raw.get("scoring", {})
    openai_raw = raw.get("openai", {})
    rate_raw = raw.get("rate_limits", {})

    return Config(
        tlds_tier1=tlds.get("tier1", Config.tlds_tier1),
        tlds_tier2=tlds.get("tier2", Config.tlds_tier2),
        scoring=ScoringConfig(
            trend_velocity_weight=scoring_raw.get("trend_velocity_weight", 25),
            commercial_value_weight=scoring_raw.get("commercial_value_weight", 25),
            typo_plausibility_weight=scoring_raw.get("typo_plausibility_weight", 20),
            domain_quality_weight=scoring_raw.get("domain_quality_weight", 15),
            risk_penalty_max=scoring_raw.get("risk_penalty_max", 15),
        ),
        openai=OpenAIConfig(
            filter_model=openai_raw.get("filter_model", "gpt-4o-mini"),
            creative_model=openai_raw.get("creative_model", "gpt-4o"),
            scorer_model=openai_raw.get("scorer_model", "gpt-4o-mini"),
        ),
        rate_limits=RateLimitsConfig(
            dns_delay_ms=rate_raw.get("dns_delay_ms", 100),
            rdap_delay_ms=rate_raw.get("rdap_delay_ms", 500),
        ),
        max_targets=raw.get("max_targets", 50),
        max_typos_per_target=raw.get("max_typos_per_target", 30),
    )
