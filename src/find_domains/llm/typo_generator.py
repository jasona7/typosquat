from __future__ import annotations

import logging

from openai import OpenAI

from find_domains.llm.client import chat_json
from find_domains.typos.generator import TypoCandidate

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert in human typing errors and misspellings. Your job is to generate \
the most realistic typos that real humans would make when trying to type a brand name.

Consider these error types:
1. **Phonetic misspellings**: How someone would spell it after hearing it spoken aloud
2. **"Heard-not-read" attempts**: Someone heard the brand name but never saw it written
3. **Mobile keyboard errors**: Fat-finger mistakes on a phone keyboard
4. **Speed-typing errors**: Common mistakes when typing quickly
5. **Memory-based errors**: How someone might remember/reconstruct the spelling
6. **Autocorrect-dodge errors**: Typos that wouldn't be caught by autocorrect

Return your response as JSON:
{
  "typos": [
    {
      "typo": "the misspelling",
      "type": "phonetic|heard_not_read|mobile|speed|memory|autocorrect",
      "confidence": 0.85,
      "explanation": "Brief explanation"
    }
  ]
}

Generate EXACTLY 15 typos. Focus on the most plausible ones that real people would actually type.\
"""


def generate_creative_typos(
    client: OpenAI,
    model: str,
    brand_name: str,
    tlds: list[str],
) -> list[TypoCandidate]:
    """Use LLM to generate creative, human-like typos for a brand name."""
    user_prompt = f"""\
Generate the 15 most likely real-human typos for the brand name: "{brand_name}"

Think about how someone might misspell this if they:
- Heard it in a podcast but never saw it written
- Were typing quickly on their phone
- Aren't sure of the exact spelling
- Have a slight accent affecting pronunciation\
"""

    result = chat_json(client, model, SYSTEM_PROMPT, user_prompt)
    typos_raw = result.get("typos", []) if isinstance(result, dict) else []

    candidates: list[TypoCandidate] = []
    seen: set[str] = set()

    for entry in typos_raw:
        typo = entry.get("typo", "").lower().strip().replace(" ", "")
        if not typo or typo in seen:
            continue
        seen.add(typo)

        confidence = min(max(float(entry.get("confidence", 0.5)), 0.0), 1.0)
        typo_type = f"llm_{entry.get('type', 'creative')}"

        for tld in tlds:
            domain = f"{typo}{tld}"
            candidates.append(TypoCandidate(
                domain=domain,
                original=brand_name,
                tld=tld,
                typo_type=typo_type,
                confidence=confidence,
            ))

    log.info("LLM generated %d creative typo candidates for %r", len(candidates), brand_name)
    return candidates
