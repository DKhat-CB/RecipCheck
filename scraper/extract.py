"""Tier 2 extraction — one messy membership page in, schema-valid JSON out.

The LLM's only job. Output shape is enforced by a Pydantic `response_schema`, so there is
no fence-stripping and no parse-failure path. Per Google's guidance the prompt carries only
the semantic rules; the schema carries the shape (no restating it, no examples).
"""
from __future__ import annotations

import os
import time
from typing import Literal, Optional

from pydantic import BaseModel

Program = Literal["NARM", "ROAM", "ASTC", "MARP", "AZA", "AHS", "ACM", "TIME_TRAVELERS"]


class Tier(BaseModel):
    name: str
    annual_price_usd: Optional[float]
    programs_unlocked: list[Program]
    adults_admitted: Optional[int]
    children_admitted: Optional[int]
    named_guests_allowed: Optional[int]
    child_free_under_age: Optional[int]
    reciprocity_explicit: bool


class GeneralAdmission(BaseModel):
    adult_price_usd: Optional[float]
    child_price_usd: Optional[float]
    child_free_under_age: Optional[int]


class PageExtraction(BaseModel):
    institution_name: str
    tiers: list[Tier]
    general_admission: GeneralAdmission
    confidence: float  # 0.0 to 1.0
    needs_manual: bool
    notes: str


EXTRACTION_PROMPT = """You extract museum membership data from the text of a single institution's
membership web page. You will be given the institution name, the reciprocal
programs it is believed to participate in (a hint from official rosters), and the
page text. Populate every field of the required structure from the page.

Institution: {name}
Believed programs (hint only): {believed}

Rules:
- Never invent a price. If a tier shows no annual price on the page, leave its price empty and set needs_manual to true.
- List a program for a tier only if the page itself ties that tier to it, by logo, name, or reciprocity language. Use the believed-programs hint only to disambiguate; do not copy it in blindly.
- Set reciprocity_explicit true for a tier only when the page explicitly connects that tier to a reciprocal program.
- If the membership content looks loaded dynamically and the page has no tier or price information, return no tiers, set needs_manual true, and say so in notes.
- If two figures conflict, for example a struck-through sale price, use the standard annual price and note the conflict.
- Report all membership tiers found, not only the reciprocal ones.
- Set confidence below 0.6 whenever anything material is uncertain, so the record routes to human review.
- Capture general admission adult and child prices and the free-child age where present; these drive the savings estimate.
- child_free_under_age is the age BELOW which children enter free. If the page says "N and under free" (e.g. "4 and under free"), set it to N+1, because children up to and including age N are free. Apply the same rule to a tier's child_free_under_age.

Page text:
{page}
"""


def _client():
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set (see .env).")
    return genai.Client(api_key=api_key)


def extract(
    page_text: str,
    institution_name: str,
    believed_programs: list[str],
    model: str = "gemini-2.5-flash",
    max_retries: int = 4,
) -> PageExtraction:
    """Call Gemini with schema-enforced output. Exponential backoff on 429/5xx."""
    from google.genai import types

    client = _client()
    prompt = EXTRACTION_PROMPT.format(
        name=institution_name,
        believed=", ".join(believed_programs) or "(none on record)",
        page=page_text,
    )
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=PageExtraction,
        temperature=0,
    )
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            return resp.parsed  # a PageExtraction instance
        except Exception as e:  # noqa: BLE001 — backoff on transient API errors
            last_err = e
            msg = str(e).lower()
            transient = "429" in msg or "503" in msg or "500" in msg or "resource" in msg or "unavailable" in msg
            if not transient or attempt == max_retries - 1:
                break
            time.sleep(2 ** attempt)  # 1, 2, 4, 8s
    raise RuntimeError(f"Gemini extraction failed for {institution_name}: {last_err}")
