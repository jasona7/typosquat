from __future__ import annotations

from dataclasses import dataclass

# QWERTY keyboard adjacency map
QWERTY_NEIGHBORS: dict[str, str] = {
    "q": "wa", "w": "qeas", "e": "wrds", "r": "etdf", "t": "ryfg",
    "y": "tugh", "u": "yijh", "i": "uojk", "o": "iplk", "p": "ol",
    "a": "qwsz", "s": "weadzx", "d": "ersfxc", "f": "rtdgcv",
    "g": "tyfhvb", "h": "yugjbn", "j": "uihknm", "k": "oijlm",
    "l": "opk", "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb",
    "b": "vghn", "n": "bhjm", "m": "njk",
}

# Common visual/phonetic substitutions
HOMOGLYPHS: dict[str, list[str]] = {
    "l": ["1", "i"],
    "i": ["1", "l"],
    "o": ["0"],
    "0": ["o"],
    "1": ["l", "i"],
    "s": ["5", "z"],
    "5": ["s"],
    "a": ["@", "4"],
    "e": ["3"],
    "b": ["6"],
    "g": ["9"],
    "t": ["7"],
    "rn": ["m"],
    "m": ["rn"],
    "cl": ["d"],
    "d": ["cl"],
    "vv": ["w"],
    "w": ["vv"],
}


@dataclass
class TypoCandidate:
    domain: str       # e.g. "gogle.com"
    original: str     # e.g. "google"
    tld: str          # e.g. ".com"
    typo_type: str    # e.g. "omission", "swap", "adjacent_key"
    confidence: float  # 0.0-1.0, how plausible this typo is


def _omissions(name: str) -> list[tuple[str, str]]:
    """Drop each character one at a time."""
    results = []
    for i in range(len(name)):
        typo = name[:i] + name[i + 1:]
        if typo and typo != name:
            results.append((typo, "omission"))
    return results


def _doublings(name: str) -> list[tuple[str, str]]:
    """Double each character."""
    results = []
    for i in range(len(name)):
        typo = name[:i] + name[i] * 2 + name[i + 1:]
        if typo != name:
            results.append((typo, "doubling"))
    return results


def _transpositions(name: str) -> list[tuple[str, str]]:
    """Swap adjacent character pairs."""
    results = []
    for i in range(len(name) - 1):
        chars = list(name)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
        typo = "".join(chars)
        if typo != name:
            results.append((typo, "transposition"))
    return results


def _adjacent_keys(name: str) -> list[tuple[str, str]]:
    """Replace each character with its QWERTY neighbors."""
    results = []
    for i in range(len(name)):
        ch = name[i].lower()
        neighbors = QWERTY_NEIGHBORS.get(ch, "")
        for neighbor in neighbors:
            typo = name[:i] + neighbor + name[i + 1:]
            if typo != name:
                results.append((typo, "adjacent_key"))
    return results


def _homoglyph_subs(name: str) -> list[tuple[str, str]]:
    """Apply homoglyph/visual substitutions."""
    results = []

    # Single character substitutions
    for i in range(len(name)):
        ch = name[i].lower()
        for replacement in HOMOGLYPHS.get(ch, []):
            if len(replacement) == 1:
                typo = name[:i] + replacement + name[i + 1:]
                if typo != name:
                    results.append((typo, "homoglyph"))

    # Multi-character pattern substitutions (e.g., rn→m)
    for pattern, replacements in HOMOGLYPHS.items():
        if len(pattern) > 1:
            for replacement in replacements:
                idx = name.find(pattern)
                while idx != -1:
                    typo = name[:idx] + replacement + name[idx + len(pattern):]
                    if typo != name:
                        results.append((typo, "homoglyph"))
                    idx = name.find(pattern, idx + 1)

    return results


# Confidence scores by typo type (how likely a real human makes this typo)
TYPO_CONFIDENCE: dict[str, float] = {
    "omission": 0.8,
    "transposition": 0.85,
    "adjacent_key": 0.7,
    "doubling": 0.6,
    "homoglyph": 0.5,
    "tld_swap": 0.4,
}


def generate_typos(name: str, tlds: list[str]) -> list[TypoCandidate]:
    """Generate all algorithmic typo candidates for a brand name across TLDs."""
    name_clean = name.lower().replace(" ", "").replace("-", "").replace(".", "")

    raw_typos: list[tuple[str, str]] = []
    raw_typos.extend(_omissions(name_clean))
    raw_typos.extend(_doublings(name_clean))
    raw_typos.extend(_transpositions(name_clean))
    raw_typos.extend(_adjacent_keys(name_clean))
    raw_typos.extend(_homoglyph_subs(name_clean))

    # Deduplicate raw typos
    seen_typos: set[str] = set()
    unique_typos: list[tuple[str, str]] = []
    for typo, typo_type in raw_typos:
        if typo not in seen_typos and typo != name_clean:
            seen_typos.add(typo)
            unique_typos.append((typo, typo_type))

    # Generate candidates across TLDs
    candidates: list[TypoCandidate] = []
    seen_domains: set[str] = set()

    for typo, typo_type in unique_typos:
        for tld in tlds:
            domain = f"{typo}{tld}"
            if domain not in seen_domains:
                seen_domains.add(domain)
                candidates.append(TypoCandidate(
                    domain=domain,
                    original=name,
                    tld=tld,
                    typo_type=typo_type,
                    confidence=TYPO_CONFIDENCE.get(typo_type, 0.5),
                ))

    # Also add the original name on different TLDs (TLD swap)
    for tld in tlds:
        domain = f"{name_clean}{tld}"
        if domain not in seen_domains:
            seen_domains.add(domain)
            candidates.append(TypoCandidate(
                domain=domain,
                original=name,
                tld=tld,
                typo_type="tld_swap",
                confidence=TYPO_CONFIDENCE["tld_swap"],
            ))

    return candidates
