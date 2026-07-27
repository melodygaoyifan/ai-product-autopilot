"""Adoption banners (§19 G1 Day 5) — the one-liners every verdict and
artifact carries so an S0 wedge is never mistaken for full adoption
(F-18.5) and a provisional toolchain never reads as first-class (F-18.4).
Empty list when the workspace opted into neither mechanism."""

from __future__ import annotations

from pathlib import Path

from ai_venture_studio.adoption.substrate import load_substrate_profile, rung_banner
from ai_venture_studio.adoption.toolchains import REGISTRY_DIR, toolchain_banner


def adoption_banners(repo_dir: str | Path) -> list[str]:
    banners = []
    profile = load_substrate_profile(repo_dir)
    if profile is not None:
        banners.append(rung_banner(profile))
    registry = Path(repo_dir) / REGISTRY_DIR
    if registry.is_dir():
        for path in sorted(registry.glob("*.yaml")):
            banner = toolchain_banner(repo_dir, path.stem)
            if banner is not None:
                banners.append(banner)
    return banners
