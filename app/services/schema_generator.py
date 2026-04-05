"""JSON-LD schema generator — rule-based with optional LLM enhancement."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.models.schemas import ExtractedData, SchemaRecommendation

logger = logging.getLogger(__name__)


# ── Public interface ─────────────────────────────────────────────────


async def generate_schema(data: ExtractedData) -> tuple[SchemaRecommendation, bool]:
    """Return ``(recommendation, llm_used)``."""

    # Try LLM path first if an API key is configured
    if settings.gemini_api_key:
        try:
            rec = await _generate_with_llm(data)
            return rec, True
        except Exception:
            logger.warning("LLM schema generation failed — falling back to rules", exc_info=True)

    return _generate_with_rules(data), False


# ── Rule-based fallback ─────────────────────────────────────────────


_PRODUCT_SIGNALS = {"price", "buy", "cart", "shop", "product", "order", "purchase", "add to cart"}
_ARTICLE_SIGNALS = {"published", "author", "blog", "article", "posted", "reading time", "min read"}
_ORG_SIGNALS = {"about us", "company", "team", "careers", "mission", "founded", "contact"}
_FAQ_SIGNALS = {"faq", "frequently asked", "questions", "q&a"}


def _detect_type(data: ExtractedData) -> tuple[str, float, str]:
    """Return ``(schema_type, confidence, reasoning)``."""
    text_blob = " ".join(
        [data.title or "", data.meta_description or ""]
        + [h.text for h in data.headings]
    ).lower()

    hits: dict[str, int] = {}
    for label, signals in [
        ("Product", _PRODUCT_SIGNALS),
        ("Article", _ARTICLE_SIGNALS),
        ("Organization", _ORG_SIGNALS),
        ("FAQPage", _FAQ_SIGNALS),
    ]:
        hits[label] = sum(1 for s in signals if s in text_blob)

    best = max(hits, key=lambda k: hits[k])
    max_hits = hits[best]

    if max_hits == 0:
        return "WebPage", 0.4, "No strong signals detected; defaulting to generic WebPage schema."

    confidence = min(0.5 + max_hits * 0.1, 0.95)
    reasoning = (
        f"Detected {max_hits} signal(s) for '{best}' schema type from page headings, "
        "title, and meta description."
    )
    return best, round(confidence, 2), reasoning


def _build_json_ld(schema_type: str, data: ExtractedData) -> dict[str, Any]:
    """Build a JSON-LD block for *schema_type*."""
    base: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": schema_type,
    }

    if data.title:
        base["name"] = data.title
    if data.meta_description:
        base["description"] = data.meta_description
    base["url"] = data.url

    if data.image_urls:
        base["image"] = data.image_urls[0]

    # Type-specific enrichments
    if schema_type == "Article":
        h1s = [h.text for h in data.headings if h.level == "h1"]
        if h1s:
            base["headline"] = h1s[0]
        if data.language:
            base["inLanguage"] = data.language
        base["wordCount"] = data.word_count

    elif schema_type == "Product":
        base.setdefault("name", data.title or "Unknown Product")

    elif schema_type == "Organization":
        base.setdefault("name", data.title or "Unknown Organisation")

    elif schema_type == "FAQPage":
        # Attempt to build FAQ items from H2/H3 pairs
        base["mainEntity"] = []
        for h in data.headings:
            if h.level in ("h2", "h3"):
                base["mainEntity"].append({
                    "@type": "Question",
                    "name": h.text,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Please provide an answer for this question.",
                    },
                })

    return base


def _generate_with_rules(data: ExtractedData) -> SchemaRecommendation:
    schema_type, confidence, reasoning = _detect_type(data)
    json_ld = _build_json_ld(schema_type, data)
    return SchemaRecommendation(
        schema_type=schema_type,
        confidence=confidence,
        reasoning=reasoning,
        json_ld=json_ld,
    )


# ── LLM-enhanced path ───────────────────────────────────────────────


async def _generate_with_llm(data: ExtractedData) -> SchemaRecommendation:
    """Call OpenRouter (Gemini) to produce a smarter schema recommendation."""
    import openai

    client = openai.AsyncOpenAI(
        api_key=settings.gemini_api_key,
        base_url=settings.llm_base_url,
    )

    headings_text = "\n".join(f"  {h.level}: {h.text}" for h in data.headings[:20])

    prompt = f"""You are an SEO / GEO (Generative Engine Optimization) expert.

Given the following extracted webpage data, recommend the single best schema.org JSON-LD markup to maximise the page's visibility to AI search engines.

URL: {data.url}
Title: {data.title or 'N/A'}
Meta description: {data.meta_description or 'N/A'}
Headings:
{headings_text or '  (none)'}
Word count: {data.word_count}
Language: {data.language or 'unknown'}

Return ONLY valid JSON with these keys:
- schema_type (string): the schema.org @type
- confidence (float 0-1): how confident you are
- reasoning (string): one-sentence explanation
- json_ld (object): the complete JSON-LD block
"""

    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)

    # Normalise fields the LLM might return in wrong types
    json_ld = parsed.get("json_ld", {})
    if isinstance(json_ld, str):
        json_ld = json.loads(json_ld)
    parsed["json_ld"] = json_ld

    confidence = parsed.get("confidence", 0.7)
    try:
        parsed["confidence"] = float(confidence)
    except (TypeError, ValueError):
        parsed["confidence"] = 0.7

    return SchemaRecommendation(**parsed)
