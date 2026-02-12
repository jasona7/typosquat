from __future__ import annotations

from pathlib import Path

import click

from find_domains.config import load_config
from find_domains.pipeline import run_pipeline


@click.group()
def main() -> None:
    """Typosquat domain finder — discover valuable typosquatting domain opportunities."""


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None, help="Path to config YAML file")
@click.option("--target", type=str, default=None, help="Scan a specific brand name instead of fetching trends")
@click.option("--output", "output_dir", type=click.Path(path_type=Path), default="results", help="Output directory for JSON results")
@click.option("--top", type=int, default=25, help="Number of top results to display")
@click.option("--skip-llm", is_flag=True, help="Skip LLM-enhanced steps (use only algorithmic typos)")
@click.option("--max-per-brand", type=int, default=None, help="Max results per brand in display ranking (default: from config)")
def scan(
    config_path: Path | None,
    target: str | None,
    output_dir: Path,
    top: int,
    skip_llm: bool,
    max_per_brand: int | None,
) -> None:
    """Run the domain scanning pipeline."""
    cfg = load_config(config_path)
    run_pipeline(cfg, target=target, output_dir=output_dir, top_n=top, skip_llm=skip_llm, max_per_brand=max_per_brand)
