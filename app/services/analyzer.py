"""GEO audit scoring — evaluates how AI-citation-ready a page is."""

from __future__ import annotations

from app.models.schemas import AuditScore, ExtractedData, GEOAuditSummary


def analyse(data: ExtractedData) -> GEOAuditSummary:
    """Return a :class:`GEOAuditSummary` with per-category scores."""
    scores: list[AuditScore] = []
    recommendations: list[str] = []

    # 1. Title
    title_score, title_rec = _score_title(data)
    scores.append(title_score)
    recommendations.extend(title_rec)

    # 2. Meta description
    meta_score, meta_rec = _score_meta(data)
    scores.append(meta_score)
    recommendations.extend(meta_rec)

    # 3. Heading structure
    heading_score, heading_rec = _score_headings(data)
    scores.append(heading_score)
    recommendations.extend(heading_rec)

    # 4. Image alt-readiness
    img_score, img_rec = _score_images(data)
    scores.append(img_score)
    recommendations.extend(img_rec)

    # 5. Content depth
    content_score, content_rec = _score_content(data)
    scores.append(content_score)
    recommendations.extend(content_rec)

    overall = int(sum(s.score for s in scores) / max(len(scores), 1))

    return GEOAuditSummary(
        overall_score=overall,
        scores=scores,
        recommendations=recommendations,
    )


# ── Private scoring helpers ──────────────────────────────────────────


def _score_title(data: ExtractedData) -> tuple[AuditScore, list[str]]:
    recs: list[str] = []
    if not data.title:
        return AuditScore(category="Title Tag", score=0, details="Missing title tag"), [
            "Add a descriptive <title> tag for AI crawlers to identify the page topic."
        ]
    length = len(data.title)
    if length < 20:
        score = 50
        recs.append("Title is too short — aim for 50-60 characters for optimal AI indexing.")
    elif length > 70:
        score = 60
        recs.append("Title exceeds 70 characters — shorten for better AI snippet extraction.")
    else:
        score = 100
    return AuditScore(category="Title Tag", score=score, details=f"Length: {length} chars"), recs


def _score_meta(data: ExtractedData) -> tuple[AuditScore, list[str]]:
    recs: list[str] = []
    if not data.meta_description:
        return AuditScore(category="Meta Description", score=0, details="Missing meta description"), [
            "Add a meta description — AI models use it to summarise PageContext."
        ]
    length = len(data.meta_description)
    if length < 50:
        score = 40
        recs.append("Meta description is too brief. Expand to 120-160 characters.")
    elif length > 160:
        score = 65
        recs.append("Meta description may be truncated. Keep under 160 chars.")
    else:
        score = 100
    return AuditScore(category="Meta Description", score=score, details=f"Length: {length} chars"), recs


def _score_headings(data: ExtractedData) -> tuple[AuditScore, list[str]]:
    recs: list[str] = []
    h1s = [h for h in data.headings if h.level == "h1"]
    h2s = [h for h in data.headings if h.level == "h2"]
    if not h1s:
        score = 20
        recs.append("No H1 heading found. Add one to anchor page topic for AI parsers.")
    elif len(h1s) > 1:
        score = 60
        recs.append(f"Multiple H1 tags found ({len(h1s)}). Use a single H1 for clarity.")
    else:
        score = 80

    if not h2s:
        score = min(score, 50)
        recs.append("Add H2 sub-headings to create a clear content hierarchy.")
    else:
        score = min(score + 20, 100)

    return AuditScore(
        category="Heading Structure",
        score=score,
        details=f"H1: {len(h1s)}, H2: {len(h2s)}, Total: {len(data.headings)}",
    ), recs


def _score_images(data: ExtractedData) -> tuple[AuditScore, list[str]]:
    recs: list[str] = []
    if not data.image_urls:
        return AuditScore(category="Images", score=30, details="No images detected"), [
            "Add at least one relevant image — visual assets improve citation quality."
        ]
    score = min(100, 50 + len(data.image_urls) * 10)
    return AuditScore(
        category="Images", score=score, details=f"{len(data.image_urls)} images found"
    ), recs


def _score_content(data: ExtractedData) -> tuple[AuditScore, list[str]]:
    recs: list[str] = []
    wc = data.word_count
    if wc < 100:
        score = 20
        recs.append("Very thin content. AI models prefer pages with 300+ words for citation.")
    elif wc < 300:
        score = 50
        recs.append("Content is light. Expanding to 500+ words can boost AI discoverability.")
    elif wc < 800:
        score = 75
    else:
        score = 100
    return AuditScore(category="Content Depth", score=score, details=f"{wc} words"), recs
