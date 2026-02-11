from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, timezone, datetime
from pathlib import Path

from find_domains.llm.scorer import ScoredDomain


def write_json_report(scored: list[ScoredDomain], output_dir: Path) -> Path:
    """Write full scored results to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = output_dir / f"{today}.json"

    data = {
        "date": today,
        "total_results": len(scored),
        "domains": [asdict(d) for d in scored],
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return path


def format_summary_table(scored: list[ScoredDomain], top_n: int = 25) -> str:
    """Format top results as a markdown table."""
    lines = [
        "## Domain Scan Results",
        "",
        f"**{len(scored)}** scored domains | Top {min(top_n, len(scored))} shown",
        "",
        "| Rank | Domain | Original | Type | Score | Trend | Value | Plausibility | Quality | Risk |",
        "|------|--------|----------|------|-------|-------|-------|-------------|---------|------|",
    ]

    for i, d in enumerate(scored[:top_n], 1):
        b = d.breakdown
        lines.append(
            f"| {i} | `{d.domain}` | {d.original} | {d.typo_type} | **{d.score}** "
            f"| {b['trend_velocity']} | {b['commercial_value']} "
            f"| {b['typo_plausibility']} | {b['domain_quality']} | {b['risk_penalty']} |"
        )

    return "\n".join(lines)


def write_github_summary(scored: list[ScoredDomain], top_n: int = 25) -> None:
    """Write a GitHub Actions step summary if running in CI."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    table = format_summary_table(scored, top_n)
    with open(summary_path, "a") as f:
        f.write(table + "\n")


def print_summary(scored: list[ScoredDomain], top_n: int = 25) -> None:
    """Print summary to stdout for CLI use."""
    if not scored:
        print("No available domains found.")
        return

    print(f"\n{'='*80}")
    print(f"  TOP {min(top_n, len(scored))} AVAILABLE TYPOSQUAT DOMAINS")
    print(f"{'='*80}\n")

    for i, d in enumerate(scored[:top_n], 1):
        b = d.breakdown
        print(f"  {i:>2}. {d.domain:<30} Score: {d.score:>5}")
        print(f"      Original: {d.original:<20} Type: {d.typo_type}")
        print(f"      Trend: {b['trend_velocity']:>4} | Value: {b['commercial_value']:>4} "
              f"| Plausible: {b['typo_plausibility']:>4} | Quality: {b['domain_quality']:>4} "
              f"| Risk: {b['risk_penalty']:>5}")
        print()
