# 🔍 GEO Audit API

A **Mini GEO (Generative Engine Optimization) Audit API** that scrapes any public webpage, evaluates its AI-citation readiness, and generates structured JSON-LD schema recommendations — all exposed through a clean FastAPI backend with a built-in web UI.

> **GEO** focuses on making web content discoverable and citable by AI search engines (ChatGPT, Perplexity, Google SGE). Structured data (JSON-LD) is one of the strongest signals these engines use.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
# 1. Clone / navigate to the project
cd project-callus

# 2. Create a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Configure environment
cp .env.example .env
# Edit .env to add your OPENAI_API_KEY for LLM-enhanced recommendations

# 5. Run the server
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000** for the web UI, or **http://localhost:8000/docs** for Swagger.

---

## 🏗️ Architecture Overview

```
┌─────────────┐     POST /api/v1/audit      ┌──────────────────┐
│  Frontend    │ ───────────────────────────► │  FastAPI Router   │
│  (index.html)│ ◄─────────────────────────── │  (routes.py)      │
└─────────────┘     AuditResponse JSON       └──────┬───────────┘
                                                     │
                                    ┌────────────────┼────────────────┐
                                    ▼                ▼                ▼
                              ┌──────────┐    ┌───────────┐   ┌──────────────┐
                              │ Scraper  │    │ Analyzer  │   │ Schema Gen   │
                              │ (httpx + │    │ (scoring  │   │ (rules or    │
                              │  BS4)    │    │  engine)  │   │  OpenAI LLM) │
                              └──────────┘    └───────────┘   └──────────────┘
```

### Components

| Component | File | Role |
|-----------|------|------|
| **API Routes** | `app/api/routes.py` | FastAPI endpoint definitions, error handling |
| **Scraper** | `app/services/scraper.py` | Async page fetching (httpx) + HTML parsing (BeautifulSoup) |
| **Analyzer** | `app/services/analyzer.py` | GEO readiness scoring across 5 categories |
| **Schema Generator** | `app/services/schema_generator.py` | Rule-based or LLM-enhanced JSON-LD generation |
| **Models** | `app/models/schemas.py` | Pydantic request/response validation |
| **Config** | `app/core/config.py` | Settings via pydantic-settings + `.env` |
| **Frontend** | `app/static/index.html` | Single-page dark-themed audit dashboard |

---

## 📡 API Usage

### `POST /api/v1/audit`

**Request:**
```json
{
  "url": "https://stripe.com"
}
```

**Response (200):**
```json
{
  "success": true,
  "extracted_data": {
    "url": "https://stripe.com",
    "title": "Stripe | Financial Infrastructure for the Internet",
    "meta_description": "Stripe powers online and in-person payment processing...",
    "headings": [
      { "level": "h1", "text": "Financial infrastructure for the internet" }
    ],
    "image_urls": ["https://stripe.com/img/v3/home/social.png"],
    "word_count": 1523,
    "language": "en"
  },
  "schema_recommendation": {
    "schema_type": "Organization",
    "confidence": 0.85,
    "reasoning": "Detected 3 signal(s) for 'Organization' schema type...",
    "json_ld": {
      "@context": "https://schema.org",
      "@type": "Organization",
      "name": "Stripe | Financial Infrastructure for the Internet",
      "url": "https://stripe.com",
      "description": "Stripe powers online and in-person payment processing..."
    }
  },
  "audit_summary": {
    "overall_score": 78,
    "scores": [
      { "category": "Title Tag", "score": 100, "details": "Length: 53 chars" },
      { "category": "Meta Description", "score": 100, "details": "Length: 135 chars" },
      { "category": "Heading Structure", "score": 80, "details": "H1: 1, H2: 4, Total: 12" },
      { "category": "Images", "score": 70, "details": "3 images found" },
      { "category": "Content Depth", "score": 100, "details": "1523 words" }
    ],
    "recommendations": [
      "No issues found — page looks well-optimised!"
    ]
  },
  "llm_used": false
}
```

### `GET /api/v1/health`
Returns `{"status": "healthy"}`.

### Error Responses

| Status | Scenario |
|--------|----------|
| 422 | Invalid URL format or non-HTML content |
| 502 | Target site returned an error |
| 504 | Timeout fetching the target URL |

---

## 🧠 Design Decision Log

### Problem Breakdown

1. **Input validation** — Ensure only valid HTTP(S) URLs are accepted → Pydantic `HttpUrl`
2. **Page scraping** — Fetch and parse HTML reliably → `httpx` (async) + `BeautifulSoup` with `lxml` parser
3. **Data extraction** — Pull title, meta, headings, images → DOM traversal with fallbacks (og: tags)
4. **GEO scoring** — Rate how AI-ready the page is → Five-category heuristic scoring engine
5. **Schema recommendation** — Suggest the best JSON-LD → Signal-matching classifier with LLM override
6. **Presentation** — Show results clearly → Embedded SPA with score rings, bar charts, copy-to-clipboard

### Alternatives Considered

| Decision | Considered | Chosen | Why |
|----------|-----------|--------|-----|
| HTTP client | `requests`, `aiohttp` | `httpx` | Async, modern API, follows redirects, built-in timeout |
| HTML parser | `Playwright`, `Selenium` | `BeautifulSoup` | Lightweight, no browser needed, fast for static pages |
| Schema detection | Pure LLM | Rule-based + LLM fallback | Works without API key, faster, cheaper; LLM adds quality when available |
| Frontend | React/Next.js | Vanilla HTML/JS | Zero build step, served by FastAPI, no extra complexity |
| Validation | Manual | Pydantic v2 | Type safety, auto-docs, serialization |

### LLM Usage Decisions

This is the most deliberate architectural choice in the project, and it reflects a core principle: **LLMs should be used where ambiguity is high and hard to enumerate, not where determinism is more valuable.**

#### Where LLM is used — and why

**JSON-LD schema type selection and generation** is the one place where an LLM genuinely outperforms rules.

A rule-based classifier counts keyword signals (`"price"` → Product, `"author"` → Article). This works for obvious cases but breaks down on real-world pages:
- A SaaS pricing page has both `"price"` and `"company"` — is it `Product` or `Organization`?
- A how-to blog post has an author *and* step-by-step instructions — `Article` or `HowTo`?
- A landing page for a software tool may warrant `SoftwareApplication`, not just `WebPage`

An LLM reads the title, meta description, and top headings holistically — the same way a human SEO expert would — and can reason about intent, not just keyword frequency. It also generates a complete, contextually accurate JSON-LD block rather than a templated fill-in.

**Implementation:** `schema_generator.py` uses a hybrid approach:
1. If `GEMINI_API_KEY` is set → call OpenRouter (Gemini Flash) via the OpenAI-compatible client
2. On any LLM failure → silently fall back to the rule-based engine
3. If no API key → rule-based only

This means the API is always functional; the LLM is an *enhancement*, not a dependency.

#### Where LLM is intentionally NOT used — and why

| Step | Why rules win here |
|------|--------------------|
| **Page scraping** | DOM parsing is deterministic, fast, and has no token cost. There is no ambiguity in extracting `<title>` or `<h1>`. Using an LLM here would add 2–4 s latency with zero quality gain. |
| **GEO scoring** | Scores must be reproducible and explainable ("Title is 14 chars, score = 50"). LLM scores would vary between calls and be impossible to audit. Heuristics give consistent, traceable results. |
| **Input validation** | Pydantic's `HttpUrl` handles URL validation at the type level, with zero latency and no hallucination risk. |
| **Error classification** | HTTP status codes and exception types are unambiguous. An LLM adds nothing here. |

#### Trade-offs

| Factor | Rule-based only | LLM-enhanced |
|--------|----------------|-------------|
| Latency | ~1–2 s total | +2–4 s for LLM call |
| Cost | Free | ~$0.001 / audit |
| Reliability | 100% deterministic | May fail / rate-limit (graceful fallback) |
| Schema quality | Good for common types (Article, Org, Product) | Handles edge cases, rare types (HowTo, Event, SoftwareApplication) |
| Explainability | Fixed scoring rubric | LLM provides a one-sentence `reasoning` field per response |

#### Why this matters for GEO

The JSON-LD block is the single output that most directly affects AI citation readiness. A wrong schema type (recommending `WebPage` when `Product` is correct) means the structured data signals the wrong entity type to crawlers and LLM training pipelines. Getting this right — especially on ambiguous pages — is where the small cost and latency of an LLM call is justified.

---

## ⚠️ Assumptions & Limitations

### Assumptions
- Target URLs serve static HTML (JS-rendered SPAs may return incomplete data)
- Pages are publicly accessible (no auth-gated content)
- English-centric signal detection for schema type classification

### Limitations
- **No JavaScript rendering** — Playwright/headless browser could be added for SPA support
- **Image alt-text not checked** — only presence of images is scored (alt auditing would require deeper crawling)
- **Single-page scope** — audits one URL at a time (no site-wide crawling)
- **Schema types** — rule engine covers Product, Article, Organization, FAQPage, and WebPage; LLM path handles any type

### Edge Cases Not Handled
- PDF or non-HTML URLs (returns 422)
- CAPTCHAs or bot-blocking (returns 502)
- Very large pages (>5MB) may slow down parsing

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

Integration tests require network access to fetch https://example.com.

---

## 📂 Project Structure

```
project-callus/
├── main.py                  # FastAPI app factory & entry point
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
├── README.md
├── app/
│   ├── core/
│   │   └── config.py        # Settings (pydantic-settings)
│   ├── models/
│   │   └── schemas.py       # Pydantic request/response models
│   ├── api/
│   │   └── routes.py        # FastAPI route handlers
│   ├── services/
│   │   ├── scraper.py       # Async web scraper
│   │   ├── analyzer.py      # GEO scoring engine
│   │   └── schema_generator.py  # JSON-LD generator (rules + LLM)
│   └── static/
│       └── index.html       # Embedded frontend dashboard
└── tests/
    └── test_api.py          # API integration tests
```

---

## 🔗 How This Supports GEO (AI Citation Readiness)

Generative AI search engines (ChatGPT Browse, Perplexity, Google AI Overviews) rely on:

1. **Structured data** — JSON-LD helps AI models understand *what* a page is about
2. **Clear headings** — Hierarchical content structure enables better extraction
3. **Meta descriptions** — Used as page summaries in AI-generated citations
4. **Content depth** — Thin pages rarely get cited; substantive content is preferred

This tool audits all four dimensions and provides actionable JSON-LD that can be dropped directly into a page's `<head>` to improve AI discoverability.

---

## 📜 License

MIT
