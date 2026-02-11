import asyncio
from unittest.mock import patch, MagicMock

import dns.resolver

from find_domains.checker.availability import _check_dns, check_availability, AvailabilityResult
from find_domains.typos.generator import TypoCandidate


class TestCheckDns:
    def test_nxdomain_returns_false(self):
        """A domain that doesn't exist should return False."""
        with patch("find_domains.checker.availability.dns.resolver.Resolver") as MockResolver:
            instance = MockResolver.return_value
            instance.resolve.side_effect = dns.resolver.NXDOMAIN()
            assert _check_dns("thisdoesnotexist12345.com") is False

    def test_has_records_returns_true(self):
        """A domain with DNS records should return True."""
        with patch("find_domains.checker.availability.dns.resolver.Resolver") as MockResolver:
            instance = MockResolver.return_value
            instance.resolve.return_value = MagicMock()  # Some records
            assert _check_dns("example.com") is True

    def test_timeout_returns_false(self):
        """DNS timeout should return False (no records found)."""
        with patch("find_domains.checker.availability.dns.resolver.Resolver") as MockResolver:
            instance = MockResolver.return_value
            instance.resolve.side_effect = dns.exception.Timeout()
            assert _check_dns("slow-domain.com") is False


class TestCheckAvailability:
    def test_dns_taken_skips_rdap(self):
        """Domains with DNS records should be marked unavailable without RDAP check."""
        candidate = TypoCandidate(
            domain="gogle.com", original="google", tld=".com",
            typo_type="omission", confidence=0.8,
        )

        with patch("find_domains.checker.availability._check_dns", return_value=True):
            results = asyncio.run(check_availability([candidate], dns_delay_ms=0, rdap_delay_ms=0))

        assert len(results) == 1
        assert results[0].available is False
        assert results[0].has_dns is True

    def test_no_dns_checks_rdap(self):
        """Domains without DNS should be checked via RDAP."""
        candidate = TypoCandidate(
            domain="xyznotreal.com", original="xyzreal", tld=".com",
            typo_type="omission", confidence=0.8,
        )

        with patch("find_domains.checker.availability._check_dns", return_value=False), \
             patch("find_domains.checker.availability._check_rdap", return_value=False):
            results = asyncio.run(check_availability([candidate], dns_delay_ms=0, rdap_delay_ms=0))

        assert len(results) == 1
        assert results[0].available is True

    def test_multiple_candidates(self):
        """Should handle a batch of candidates."""
        candidates = [
            TypoCandidate(domain=f"test{i}.com", original="test", tld=".com",
                          typo_type="omission", confidence=0.8)
            for i in range(5)
        ]

        dns_results = [True, False, True, False, False]

        call_count = 0
        def mock_dns(domain):
            nonlocal call_count
            result = dns_results[call_count]
            call_count += 1
            return result

        with patch("find_domains.checker.availability._check_dns", side_effect=mock_dns), \
             patch("find_domains.checker.availability._check_rdap", return_value=False):
            results = asyncio.run(check_availability(candidates, dns_delay_ms=0, rdap_delay_ms=0))

        assert len(results) == 5
        available = [r for r in results if r.available]
        assert len(available) == 3  # 3 passed DNS check, all confirmed by RDAP
