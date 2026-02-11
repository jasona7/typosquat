import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from find_domains.config import Config, ScoringConfig
from find_domains.llm.scorer import ScoredDomain, score_domains, _tld_quality_score, _domain_length_score
from find_domains.checker.availability import AvailabilityResult
from find_domains.report.github_summary import format_summary_table, write_json_report
from find_domains.trends.google_trends import TrendItem
from find_domains.typos.generator import TypoCandidate


class TestScorer:
    def _make_result(self, domain="gogle.com", original="google", tld=".com",
                     typo_type="omission", confidence=0.8):
        candidate = TypoCandidate(
            domain=domain, original=original, tld=tld,
            typo_type=typo_type, confidence=confidence,
        )
        return AvailabilityResult(
            candidate=candidate, has_dns=False, rdap_registered=False, available=True,
        )

    def test_score_range(self):
        results = [self._make_result()]
        velocities = {"google": 2.0}
        scoring = ScoringConfig()

        scored = score_domains(None, "", results, velocities, scoring, skip_llm=True)

        assert len(scored) == 1
        assert 0 <= scored[0].score <= 100

    def test_higher_velocity_higher_score(self):
        results = [self._make_result()]
        scoring = ScoringConfig()

        low = score_domains(None, "", results, {"google": 0.1}, scoring, skip_llm=True)
        high = score_domains(None, "", results, {"google": 3.0}, scoring, skip_llm=True)

        assert high[0].score > low[0].score

    def test_breakdown_keys(self):
        results = [self._make_result()]
        scoring = ScoringConfig()
        scored = score_domains(None, "", results, {"google": 1.0}, scoring, skip_llm=True)

        expected_keys = {"trend_velocity", "commercial_value", "typo_plausibility",
                         "domain_quality", "risk_penalty"}
        assert set(scored[0].breakdown.keys()) == expected_keys

    def test_tld_quality(self):
        assert _tld_quality_score(".com") > _tld_quality_score(".xyz")
        assert _tld_quality_score(".ai") > _tld_quality_score(".me")

    def test_domain_length(self):
        assert _domain_length_score("ab.com") > _domain_length_score("abcdefghijklmnop.com")

    def test_sorted_descending(self):
        results = [
            self._make_result(domain="gogle.com", confidence=0.3),
            self._make_result(domain="googl.com", confidence=0.9),
        ]
        scoring = ScoringConfig()
        scored = score_domains(None, "", results, {"google": 1.0}, scoring, skip_llm=True)

        assert scored[0].score >= scored[1].score


class TestReport:
    def test_format_summary_table(self):
        scored = [
            ScoredDomain(
                domain="gogle.com", original="google", tld=".com",
                typo_type="omission", score=75.5,
                breakdown={
                    "trend_velocity": 20.0, "commercial_value": 22.0,
                    "typo_plausibility": 16.0, "domain_quality": 12.0,
                    "risk_penalty": -5.5,
                },
            ),
        ]

        table = format_summary_table(scored, top_n=10)
        assert "gogle.com" in table
        assert "75.5" in table
        assert "Domain Scan Results" in table

    def test_write_json_report(self, tmp_path):
        scored = [
            ScoredDomain(
                domain="gogle.com", original="google", tld=".com",
                typo_type="omission", score=75.5,
                breakdown={
                    "trend_velocity": 20.0, "commercial_value": 22.0,
                    "typo_plausibility": 16.0, "domain_quality": 12.0,
                    "risk_penalty": -5.5,
                },
            ),
        ]

        path = write_json_report(scored, tmp_path)
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["total_results"] == 1
        assert data["domains"][0]["domain"] == "gogle.com"
        assert data["domains"][0]["score"] == 75.5
