from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import dns.resolver
import httpx

from find_domains.typos.generator import TypoCandidate

log = logging.getLogger(__name__)

# RDAP bootstrap for common TLDs
RDAP_SERVERS: dict[str, str] = {
    ".com": "https://rdap.verisign.com/com/v1",
    ".net": "https://rdap.verisign.com/net/v1",
    ".org": "https://rdap.org/org/v1",
    ".io": "https://rdap.nic.io",
    ".ai": "https://rdap.nic.ai",
    ".co": "https://rdap.nic.co",
    ".app": "https://rdap.nic.google",
    ".dev": "https://rdap.nic.google",
    ".xyz": "https://rdap.nic.xyz",
    ".me": "https://rdap.nic.me",
    ".gg": "https://rdap.nic.gg",
    ".tv": "https://rdap.nic.tv",
}

# IANA bootstrap URL
RDAP_BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"


@dataclass
class AvailabilityResult:
    candidate: TypoCandidate
    has_dns: bool
    rdap_registered: bool | None  # None = couldn't check
    available: bool


def _check_dns(domain: str) -> bool:
    """Check if a domain has any DNS records. Returns True if records exist."""
    resolver = dns.resolver.Resolver()
    resolver.timeout = 3
    resolver.lifetime = 3

    for rdtype in ["A", "AAAA", "CNAME", "MX"]:
        try:
            resolver.resolve(domain, rdtype)
            return True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            continue
        except dns.exception.Timeout:
            continue
        except Exception:
            continue

    return False


async def _check_rdap(client: httpx.AsyncClient, domain: str, tld: str) -> bool | None:
    """Check RDAP for domain registration. Returns True if registered, False if not, None if error."""
    # Find the RDAP server for this TLD
    server = RDAP_SERVERS.get(tld)
    if not server:
        return None

    url = f"{server}/domain/{domain}"
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code == 200:
            return True
        elif resp.status_code == 404:
            return False
        else:
            return None
    except Exception:
        log.debug("RDAP check failed for %s", domain, exc_info=True)
        return None


async def check_availability(
    candidates: list[TypoCandidate],
    dns_delay_ms: int = 100,
    rdap_delay_ms: int = 500,
) -> list[AvailabilityResult]:
    """Check domain availability for a list of typo candidates.

    Strategy:
    1. DNS check first (fast) — if records exist, domain is taken
    2. For domains with no DNS records, confirm via RDAP
    """
    results: list[AvailabilityResult] = []
    dns_passed: list[TypoCandidate] = []

    # Phase 1: DNS checks
    for candidate in candidates:
        has_dns = _check_dns(candidate.domain)
        if has_dns:
            results.append(AvailabilityResult(
                candidate=candidate,
                has_dns=True,
                rdap_registered=None,
                available=False,
            ))
        else:
            dns_passed.append(candidate)

        await asyncio.sleep(dns_delay_ms / 1000.0)

    # Phase 2: RDAP confirmation for DNS-clear domains
    if dns_passed:
        async with httpx.AsyncClient(timeout=10) as client:
            for candidate in dns_passed:
                rdap_result = await _check_rdap(client, candidate.domain, candidate.tld)

                if rdap_result is False:
                    available = True
                elif rdap_result is True:
                    available = False
                else:
                    # Couldn't confirm via RDAP — assume likely available if no DNS
                    available = True

                results.append(AvailabilityResult(
                    candidate=candidate,
                    has_dns=False,
                    rdap_registered=rdap_result,
                    available=available,
                ))

                await asyncio.sleep(rdap_delay_ms / 1000.0)

    return results
