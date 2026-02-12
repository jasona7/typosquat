import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from find_domains.config import Config, ScoringConfig
from find_domains.llm.scorer import ScoredDomain, score_domains, _tld_quality_score, _domain_length_score
from find_domains.checker.availability import AvailabilityResult
from find_domains.pipeline import _diversify
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

    def test_nonlinear_risk_penalty(self):
        """High UDRP risk should be penalised more than linearly."""
        results = [self._make_result()]
        scoring = ScoringConfig(risk_penalty_max=25)

        # Patch LLM assessments to inject different UDRP levels
        with patch("find_domains.llm.scorer.chat_json") as mock_chat:
            # Low risk brand (udrp 3)
            mock_chat.return_value = {"assessments": [
                {"brand": "google", "estimated_cpc": 5.0, "commercial_niche": "tech", "udrp_risk": 3}
            ]}
            low_risk = score_domains(
                MagicMock(), "gpt-4o-mini", results, {"google": 1.0}, scoring,
            )

            # High risk brand (udrp 9)
            mock_chat.return_value = {"assessments": [
                {"brand": "google", "estimated_cpc": 5.0, "commercial_niche": "tech", "udrp_risk": 9}
            ]}
            high_risk = score_domains(
                MagicMock(), "gpt-4o-mini", results, {"google": 1.0}, scoring,
            )

        # The gap between low and high risk should be large
        gap = low_risk[0].score - high_risk[0].score
        # With exponential penalty (1.5 exponent) and max=25:
        #   risk 3 penalty = (0.3)^1.5 * 25 ≈ 4.1
        #   risk 9 penalty = (0.9)^1.5 * 25 ≈ 21.4
        #   gap ≈ 17.3
        assert gap > 15, f"Expected gap > 15 between low/high UDRP risk, got {gap}"


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


class TestDiversify:
    def _make_scored(self, domain, original, score):
        return ScoredDomain(
            domain=domain, original=original, tld=".com",
            typo_type="omission", score=score, breakdown={},
        )

    def test_caps_per_brand(self):
        scored = [
            self._make_scored("wndows.com", "Windows", 90),
            self._make_scored("windws.com", "Windows", 88),
            self._make_scored("windos.com", "Windows", 85),
            self._make_scored("winows.com", "Windows", 80),
            self._make_scored("winddows.com", "Windows", 75),
            self._make_scored("slacc.com", "Slack", 70),
        ]

        result = _diversify(scored, max_per_brand=3)

        windows_count = sum(1 for d in result if d.original == "Windows")
        assert windows_count == 3
        assert len(result) == 4  # 3 Windows + 1 Slack

    def test_preserves_order(self):
        scored = [
            self._make_scored("wndows.com", "Windows", 90),
            self._make_scored("slacc.com", "Slack", 85),
            self._make_scored("windws.com", "Windows", 80),
        ]

        result = _diversify(scored, max_per_brand=1)

        assert result[0].domain == "wndows.com"
        assert result[1].domain == "slacc.com"
        assert len(result) == 2

    def test_case_insensitive_brand_matching(self):
        scored = [
            self._make_scored("a.com", "Windows", 90),
            self._make_scored("b.com", "windows", 85),
            self._make_scored("c.com", "WINDOWS", 80),
        ]

        result = _diversify(scored, max_per_brand=2)

        assert len(result) == 2
