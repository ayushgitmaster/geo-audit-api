# GEO Audit API — Submission Document

**Project:** Mini GEO Audit API  
**Stack:** Python 3.11, FastAPI, httpx, BeautifulSoup4 (lxml), Pydantic v2, OpenRouter (Gemini Flash)

---

## 1. Setup Instructions

### Prerequisites
- Python 3.11+
- pip

### Local Setup

```bash
# Navigate to project
cd project-callus

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment (optional — enables LLM-enhanced schema generation)
cp .env.example .env
# Edit .env and set: GEMINI_API_KEY=your_openrouter_key

# Start the server
uvicorn main:app --reload --port 8000
```

- Web UI: http://localhost:8000  
- Swagger docs: http://localhost:8000/docs  
- Health check: http://localhost:8000/api/v1/health

### Running Tests

```bash
pytest tests/ -v
```

---

## 2. Architecture Overview

```
Browser / curl
     │
     │  POST /api/v1/audit  { "url": "https://stripe.com" }
     ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI  (main.py + app/api/routes.py)                 │
│  - Validates URL via Pydantic HttpUrl                   │
│  - Orchestrates the three-service pipeline              │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┼───────────────────┐
    ▼          ▼                   ▼
┌─────────┐  ┌──────────────┐  ┌──────────────────────┐
│ Scraper │  │  Analyzer    │  │  Schema Generator    │
│ httpx   │  │  (heuristic  │  │  Rule-based          │
│ + lxml  │  │   scorer)    │  │  + optional LLM      │
└────┬────┘  └──────┬───────┘  └──────────┬───────────┘
     │              │                      │
     └──────────────┴──────────────────────┘
                         │
                    AuditResponse
                    (JSON to client)
```

### Component Responsibilities

| File | Responsibility |
|------|---------------|
| `main.py` | App factory, CORS, static file serving |
| `app/api/routes.py` | Route handlers, error shaping into `ErrorResponse` format |
| `app/services/scraper.py` | Async fetch with SSL fallback, BeautifulSoup extraction (title, meta, headings, images, word count, language) |
| `app/services/analyzer.py` | Five-category GEO scoring engine with per-category details |
| `app/services/schema_generator.py` | Rule-based signal classifier + LLM override via OpenRouter |
| `app/models/schemas.py` | Pydantic v2 request/response models |
| `app/core/config.py` | Environment settings via pydantic-settings |
| `app/static/index.html` | Single-file dark-themed SPA dashboard |
| `tests/` | Integration tests via httpx ASGITransport (no live server needed) |

---

## 3. Design Decision Log

This section documents how the problem was broken down and what choices were made at each step.

---

### Step 1 — What does the input/output contract look like?

**Problem:** Accept a URL, return structured audit data. The shape of the output drives every other decision.

**Options considered:**
- Free-form text output (rejected — not machine-readable, hard to build a UI on)
- Flat JSON (considered but abandoned — no validation, easy to drift)
- Pydantic models (chosen)

**Decision:** Define strict Pydantic models first (`AuditRequest`, `ExtractedData`, `SchemaRecommendation`, `GEOAuditSummary`, `AuditResponse`). This gives free auto-documentation in Swagger, serialisation guarantees, and makes each service's inputs/outputs explicit contracts rather than implicit dict assumptions.

---

### Step 2 — How to fetch pages reliably?

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| `requests` (sync) | Simple | Blocks event loop, no async |
| `aiohttp` | Async | More complex API, less ergonomic |
| `Playwright` / `Selenium` | Renders JS | Heavy dependency, slow startup |
| `httpx` (async) | Modern, async, follows redirects, type-safe | — |

**Decision:** `httpx` with async client. JS-rendered SPAs are an acknowledged limitation — adding Playwright is a clear extension path but adds significant complexity for a prototype.

**Edge case handled:** Many sites use self-signed or chain-incomplete SSL certificates (common on corporate and regional websites). A naked `SSLError` would fail the request entirely. The scraper detects SSL-specific errors by walking the full exception `__cause__` chain (since `httpx` wraps `ssl.SSLError` through `httpcore`) and retries with `verify=False` only in that case — all other `ConnectError` types still propagate.

**Parser choice:** `lxml` over Python's built-in `html.parser` — faster and more lenient with malformed HTML, which is the majority of real-world pages.

---

### Step 3 — How to score GEO readiness?

**Options considered:**
- Ask an LLM to score the page (rejected — non-deterministic, expensive, can't be audited)
- Single composite score only (rejected — not actionable, no insight into what to fix)
- Per-category heuristic scoring (chosen)

**Decision:** Five independent scoring functions, each returning a score (0–100) and a `details` string. Categories:
1. **Title Tag** — length check (20–70 chars optimal)
2. **Meta Description** — presence and length (50–160 chars)
3. **Heading Structure** — H1 count (exactly one), H2 presence
4. **Images** — presence and count (visual assets improve citation quality)
5. **Content Depth** — word count thresholds (<100 thin, 300+ good, 800+ strong)

The overall score is the arithmetic mean. This is intentionally simple — explainable, testable, and consistent across audits.

---

### Step 4 — Rule-based vs LLM for schema recommendation

This is the most important architectural decision in the project.

**Why the schema step is uniquely suited to an LLM:**

A rule-based classifier counts keyword signals in the page text:
- `"price"`, `"buy"`, `"cart"` → Product  
- `"author"`, `"published"`, `"blog"` → Article  
- `"about us"`, `"company"`, `"team"` → Organization

This works for clear-cut cases. But real pages are messy:
- A SaaS pricing page has both `"price"` and `"company"` signals — is it `Product` or `Organization`?
- A how-to tutorial has an author and step-by-step instructions — `Article` or `HowTo`?
- A developer tool landing page may warrant `SoftwareApplication`, which the rule engine doesn't even know exists

An LLM reads the page holistically — title, meta description, and top headings — and reasons about *intent* rather than keyword frequency. It also generates contextually accurate JSON-LD values (real `name`, `description`, `url` fields) rather than template stubs.

**Why NOT to use LLM for everything:**
- Scraping: DOM parsing is deterministic. There is no "ambiguity" in extracting `<title>`. LLM adds latency and cost with zero quality gain.
- Scoring: Scores must be reproducible. "Title is 14 chars, score = 50" is auditable. An LLM score varies between calls.
- Validation: Pydantic handles URL validation at zero latency.

**Implementation — hybrid approach:**
1. If `GEMINI_API_KEY` is configured → call OpenRouter (Gemini 2.0 Flash) via OpenAI-compatible client
2. On any LLM failure (network, rate limit, malformed response) → silently fall back to rule-based engine and log a warning
3. No API key → rule-based only, full functionality

The response includes an `llm_used` boolean so the client always knows which path was taken.

**Response normalisation:** The LLM occasionally returns `json_ld` as a JSON string rather than an object, or `confidence` as a string. The schema generator normalises both before Pydantic validation — making the LLM integration resilient to model behaviour drift.

---

### Step 5 — Error response consistency

FastAPI's default `HTTPException` returns `{"detail": "..."}`. The API's documented `ErrorResponse` model uses `{"success": false, "error": "...", "detail": "..."}`. These were inconsistent — the Swagger docs said one thing but the API returned another.

**Fix:** Replaced all `raise HTTPException(...)` calls in `routes.py` with `return JSONResponse(content=ErrorResponse(...).model_dump())`. Error responses now always match the documented schema, regardless of the failure mode.

---

### Step 6 — Frontend

**Options:**
- React / Next.js (rejected — build step required, separate dev server, overkill)
- Vanilla HTML/JS served by FastAPI (chosen)

A single `index.html` file is mounted as a static file and served at `/`. No build step, no separate process, deployable as a single `uvicorn` command. The tradeoff is no component model or state management — acceptable for an audit tool where the entire interaction is one request-response cycle.

---

## 4. Key Technical Decisions — Walkthrough Notes

*(Answers to the three walkthrough questions for the video recording)*

---

### Q1: 2–3 Key Technical Decisions and Alternatives Considered

**Decision 1: Hybrid LLM + rule-based schema generation**  
The rule engine is the default and always works. The LLM is layered on top when an API key is available. This means the system degrades gracefully — a rate limit or key expiry silently falls back to rules rather than returning a 500. The LLM is only invoked for the schema step because that is the only step with genuine ambiguity that rules handle poorly.

**Decision 2: lxml parser + SSL retry with cause-chain inspection**  
Two real-world reliability decisions. Using `lxml` over `html.parser` handles the majority of malformed production HTML silently. The SSL retry logic walks `exc.__cause__` and `exc.__context__` recursively because `httpx` wraps `ssl.SSLError` inside `httpcore.ConnectError`, so a naive `isinstance(exc, ssl.SSLError)` check would never trigger — missing SSL fallback for a large class of sites.

**Decision 3: ErrorResponse-shaped JSON for all error paths**  
All error responses (scrape failure, timeout, invalid content) return `{"success": false, "error": "...", "detail": "..."}` via `JSONResponse`. This means API consumers can write a single error handler regardless of status code. The Swagger docs and the actual API behaviour match.

---

### Q2: Redesigning for 50+ Pages (Site-Wide Audit)

The current architecture is a linear synchronous pipeline: one URL in, one response out. For 50+ pages, this needs to become a distributed, parallel, fault-tolerant system.

**Proposed architecture:**

```
User submits domain
        │
        ▼
┌──────────────────┐
│  Crawler Agent   │  Discovers all URLs (sitemap.xml, crawl links)
│  (async, BFS)    │  Outputs: list of URLs + page metadata
└────────┬─────────┘
         │  URL queue (Redis / SQS)
         ▼
┌────────────────────────────────┐
│  Worker Pool (N parallel)      │
│  Each worker: scrape → score → schema │
│  httpx async, semaphore-limited │
└────────┬───────────────────────┘
         │  Results → PostgreSQL / S3
         ▼
┌──────────────────┐
│  Aggregator Agent│  Rolls up per-page scores to site-wide score
│                  │  Identifies patterns: "70% of pages missing H1"
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Report Generator│  Prioritised recommendations, site-level JSON-LD
└──────────────────┘
```

**Multi-agent pattern:**
- **Crawler agent** — deterministic BFS with politeness delay, respects `robots.txt`
- **Per-page worker agents** — each runs the current scrape → score pipeline; stateless and horizontally scalable
- **Aggregator agent** — could be LLM-assisted: after collecting all page scores, an LLM prompt with the site's overall pattern ("30% of pages are thin content, mostly /blog/ prefix") can generate site-level strategic recommendations that rule-based aggregation would miss

**Parallel processing:** `asyncio.gather` with a `Semaphore` to cap concurrency (respect target server rate limits). Workers write results to a queue as they complete, so the frontend can show progress.

**Failure handling:**
- Per-page failures are isolated — a 403 on one page doesn't abort the rest
- Failed URLs are written to a retry queue with exponential backoff
- Each result stores a `status` field: `success | skipped | failed`
- A site audit is complete when all URLs are terminal (not pending/retrying)

**Where LLMs add value vs deterministic logic at scale:**
- **Deterministic everywhere except:** schema generation (per page, as today) and site-level pattern interpretation (aggregator)
- **Not LLM:** crawling, scoring, deduplication, URL normalisation, sitemap parsing — all unambiguous tasks where rules are faster, cheaper, and auditable
- **LLM for aggregation reasoning:** "These 12 product pages all lack `Product` schema and have thin content — priority: add JSON-LD and expand copy" — this synthesis is hard to express as rules

---

### Q3: Biggest Weakness and How to Improve It

**Biggest weakness: no JavaScript rendering**

The scraper uses `httpx` + BeautifulSoup — it sees only the HTML the server returns on first response. Modern websites (React, Next.js, Vue SPAs) often return a near-empty HTML shell; all content is injected by JavaScript after the page loads. For these sites, the scraper extracts:
- Title: empty or a loader string
- Meta description: often missing (set dynamically by React Helmet)
- Headings: 0 (rendered by JS)
- Word count: ~30 words (skeleton HTML only)

This produces misleading audit scores — a perfectly optimised React site looks like a bare page.

**How to fix it with more time:**

*Option A (pragmatic):* Add a `?render=true` query parameter that triggers a Playwright headless browser path. Keep the fast httpx path as default; only pay the 3–5 s Playwright startup cost when explicitly requested or when the initial scrape returns fewer than 50 words.

*Option B (detection-first):* After scraping, check `word_count < 50 AND headings == 0`. If true, classify the page as "JS-rendered, data may be incomplete" and include a warning in the audit response rather than silently returning low scores. This is a one-line heuristic that at minimum makes the limitation visible to the user.

*Option C (infrastructure):* Run a persistent Playwright browser pool (e.g., using `playwright-pool`) as a sidecar service. The scraper checks a "pre-rendered HTML cache" first (pages rendered on demand and cached for 1 hour via Redis), falling back to live rendering. This adds latency only on cache miss.

**Secondary weakness: English-centric signal detection**

The schema type classifier uses English keyword signals (`"price"`, `"author"`, `"about us"`). Non-English pages default to `WebPage` regardless of content. Fix: use the detected `lang` attribute to select a language-specific signal dictionary, or rely exclusively on the LLM path for non-English pages.

---

## 5. Assumptions and Known Limitations

### Assumptions
- Target URLs serve static or server-rendered HTML
- Pages are publicly accessible (no authentication, no CAPTCHA)
- English-language pages for optimal rule-based schema classification
- The OpenRouter API is available when `GEMINI_API_KEY` is set

### Known Limitations

| Limitation | Impact | Possible Fix |
|-----------|--------|-------------|
| No JS rendering | SPAs return empty/thin data | Add Playwright headless path |
| Single-URL scope | No site-wide audit | URL queue + worker pool (see Q2) |
| Image alt-text not audited | Score doesn't reflect alt-text quality | Extract `alt` attributes and score them |
| English-centric classifier | Non-English pages always score `WebPage` | Language-specific signal sets |
| No caching | Same URL re-scrapes every time | Redis TTL cache on URL → ExtractedData |
| Schema type coverage | Rule engine knows 5 types; LLM knows all | LLM fallback already handles this |
| PDF / file URLs | Returns 422 (correct but abrupt) | Could return a more helpful message |
| Bot-blocked sites (403, CAPTCHA) | Returns 502 | No fix — scraping ethics require respecting blocks |

---

## 6. Source Code

Repository / demo folder URL: *(add your GitHub or Google Drive link here)*

To run locally, see **Section 1 — Setup Instructions** above.
