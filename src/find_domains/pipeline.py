from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click

from find_domains.checker.availability import AvailabilityResult, check_availability
from find_domains.config import Config
from find_domains.llm.client import get_client
from find_domains.llm.scorer import ScoredDomain, score_domains
from find_domains.llm.trend_filter import filter_trends
from find_domains.llm.typo_generator import generate_creative_typos
from find_domains.report.github_summary import (
    print_summary,
    write_github_summary,
    write_json_report,
)
from find_domains.trends.google_trends import TrendItem, fetch_google_trends
from find_domains.trends.hackernews import fetch_hackernews
from find_domains.typos.generator import TypoCandidate, generate_typos

log = logging.getLogger(__name__)


def _diversify(scored: list[ScoredDomain], max_per_brand: int) -> list[ScoredDomain]:
    """Limit results to at most *max_per_brand* entries per original brand."""
    brand_counts: dict[str, int] = {}
    diversified: list[ScoredDomain] = []
    for item in scored:
        key = item.original.lower()
        if brand_counts.get(key, 0) < max_per_brand:
            diversified.append(item)
            brand_counts[key] = brand_counts.get(key, 0) + 1
    return diversified


def _collect_trends(target: str | None) -> list[TrendItem]:
    """Stage 1: Collect trends from all sources, or use a manual target."""
    if target:
        click.echo(f"Using manual target: {target}")
        return [TrendItem(name=target, source="manual", velocity=2.0)]

    click.echo("Collecting trends...")
    google = fetch_google_trends()
    click.echo(f"  Google Trends: {len(google)} items")

    hn = fetch_hackernews()
    click.echo(f"  Hacker News: {len(hn)} items")

    # Merge and deduplicate, keeping highest velocity
    merged: dict[str, TrendItem] = {}
    for item in google + hn:
        key = item.name.lower()
        if key not in merged or item.velocity > merged[key].velocity:
            merged[key] = item

    all_trends = list(merged.values())
    click.echo(f"  Total unique trends: {len(all_trends)}")
    return all_trends


def _filter_targets(
    trends: list[TrendItem],
    cfg: Config,
    skip_llm: bool,
) -> list[dict]:
    """Stage 2: Use LLM to filter trends to best targets."""
    if skip_llm:
        # When skipping LLM, treat all trends as targets
        return [{"name": t.name} for t in trends[:cfg.max_targets]]

    click.echo("Filtering trends with LLM...")
    client = get_client()
    targets = filter_trends(client, cfg.openai.filter_model, trends, cfg.max_targets)
    click.echo(f"  Selected {len(targets)} targets")
    return targets


def _generate_all_typos(
    targets: list[dict],
    cfg: Config,
    skip_llm: bool,
) -> list[TypoCandidate]:
    """Stage 3: Generate typo candidates (algorithmic + LLM-enhanced)."""
    click.echo("Generating typo candidates...")
    all_candidates: list[TypoCandidate] = []
    seen_domains: set[str] = set()

    tlds = cfg.tlds_tier1  # Use tier1 TLDs for initial scan

    for target in targets:
        name = target["name"]

        # Algorithmic typos
        algo_candidates = generate_typos(name, tlds)

        # LLM-enhanced typos
        llm_candidates: list[TypoCandidate] = []
        if not skip_llm:
            try:
                client = get_client()
                llm_candidates = generate_creative_typos(
                    client, cfg.openai.creative_model, name, tlds,
                )
            except Exception:
                log.warning("LLM typo generation failed for %r", name, exc_info=True)

        # Merge and deduplicate
        for c in algo_candidates + llm_candidates:
            if c.domain not in seen_domains:
                seen_domains.add(c.domain)
                all_candidates.append(c)

        # Cap per target
        target_count = sum(1 for c in all_candidates if c.original == name)
        if target_count > cfg.max_typos_per_target:
            # Keep only the highest confidence ones for this target
            target_cands = [c for c in all_candidates if c.original == name]
            target_cands.sort(key=lambda c: c.confidence, reverse=True)
            keep = {c.domain for c in target_cands[:cfg.max_typos_per_target]}
            all_candidates = [
                c for c in all_candidates
                if c.original != name or c.domain in keep
            ]

    click.echo(f"  Generated {len(all_candidates)} unique candidates")
    return all_candidates


def _check_domains(
    candidates: list[TypoCandidate],
    cfg: Config,
) -> list[AvailabilityResult]:
    """Stage 4: Check domain availability."""
    click.echo(f"Checking availability for {len(candidates)} domains...")
    results = asyncio.run(check_availability(
        candidates,
        dns_delay_ms=cfg.rate_limits.dns_delay_ms,
        rdap_delay_ms=cfg.rate_limits.rdap_delay_ms,
    ))
    available = [r for r in results if r.available]
    click.echo(f"  Available: {len(available)} / {len(results)}")
    return available


def _score_results(
    available: list[AvailabilityResult],
    trends: list[TrendItem],
    cfg: Config,
    skip_llm: bool,
) -> list[ScoredDomain]:
    """Stage 5: Score available domains."""
    click.echo("Scoring domains...")

    trend_velocities = {t.name.lower(): t.velocity for t in trends}

    client = None if skip_llm else get_client()
    scored = score_domains(
        client,
        cfg.openai.scorer_model,
        available,
        trend_velocities,
        cfg.scoring,
        skip_llm=skip_llm,
    )

    click.echo(f"  Scored {len(scored)} domains")
    return scored


def run_pipeline(
    cfg: Config,
    target: str | None = None,
    output_dir: Path = Path("results"),
    top_n: int = 25,
    skip_llm: bool = False,
    max_per_brand: int | None = None,
) -> list[ScoredDomain]:
    """Run the full domain scanning pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Stage 1: Collect trends
    trends = _collect_trends(target)

    # Stage 2: Filter to best targets
    targets = _filter_targets(trends, cfg, skip_llm)
    if not targets:
        click.echo("No targets found. Exiting.")
        return []

    # Stage 3: Generate typo candidates
    candidates = _generate_all_typos(targets, cfg, skip_llm)
    if not candidates:
        click.echo("No typo candidates generated. Exiting.")
        return []

    # Stage 4: Check availability
    available = _check_domains(candidates, cfg)
    if not available:
        click.echo("No available domains found. Exiting.")
        return []

    # Stage 5: Score results
    scored = _score_results(available, trends, cfg, skip_llm)

    # Stage 6: Diversify for display ranking
    brand_limit = max_per_brand if max_per_brand is not None else cfg.max_per_brand
    display = _diversify(scored, brand_limit)

    # Stage 7: Report (JSON gets all results; display list is diversified)
    json_path = write_json_report(scored, output_dir)
    click.echo(f"Full results written to {json_path}")

    write_github_summary(display, top_n)
    print_summary(display, top_n)

    return scored
