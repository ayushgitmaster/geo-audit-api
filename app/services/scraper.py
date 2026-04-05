"""Web scraper — extracts structured page data from a public URL."""

from __future__ import annotations

import logging
import re
import ssl
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import settings
from app.models.schemas import ExtractedData, HeadingItem

logger = logging.getLogger(__name__)


def _is_ssl_error(exc: BaseException) -> bool:
    """Return True if *exc* or any exception in its cause chain is an SSL error.

    httpx wraps ssl.SSLError inside httpcore.ConnectError before re-raising as
    httpx.ConnectError, so we must walk the full __cause__ chain.
    """
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLError):
            return True
        # Also catch by message for any future httpcore/httpx wrapping changes
        if "ssl" in str(current).lower() or "certificate" in str(current).lower():
            return True
        current = current.__cause__ or current.__context__
    return False


async def scrape_url(url: str) -> ExtractedData:
    """Fetch *url* and return structured :class:`ExtractedData`."""

    headers = {"User-Agent": settings.USER_AGENT}

    try:
        async with httpx.AsyncClient(
            timeout=settings.REQUEST_TIMEOUT,
            follow_redirects=True,
            verify=True,
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        # Only disable SSL verification when the failure is SSL-related.
        # httpx wraps ssl.SSLError through httpcore, so we walk the cause chain.
        if not _is_ssl_error(exc):
            raise
        logger.warning("SSL verification failed for %s — retrying without verify", url)
        async with httpx.AsyncClient(
            timeout=settings.REQUEST_TIMEOUT,
            follow_redirects=True,
            verify=False,
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ValueError(
            f"URL did not return HTML content (got {content_type})"
        )

    soup = BeautifulSoup(response.text, "lxml")

    title = _extract_title(soup)
    meta_description = _extract_meta_description(soup)
    headings = _extract_headings(soup)
    image_urls = _extract_images(soup, url)
    word_count = _count_words(soup)
    language = _detect_language(soup)

    return ExtractedData(
        url=url,
        title=title,
        meta_description=meta_description,
        headings=headings,
        image_urls=image_urls,
        word_count=word_count,
        language=language,
    )


# ── Private helpers ──────────────────────────────────────────────────


def _extract_title(soup: BeautifulSoup) -> str | None:
    # Prefer <title> tag, fall back to og:title
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    og = soup.find("meta", property="og:title")
    if og and isinstance(og, Tag) and og.get("content"):
        return str(og["content"]).strip()
    return None


def _extract_meta_description(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and isinstance(tag, Tag) and tag.get("content"):
        return str(tag["content"]).strip()
    og = soup.find("meta", property="og:description")
    if og and isinstance(og, Tag) and og.get("content"):
        return str(og["content"]).strip()
    return None


def _extract_headings(soup: BeautifulSoup) -> list[HeadingItem]:
    headings: list[HeadingItem] = []
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        text = tag.get_text(separator=" ", strip=True)
        if text:
            headings.append(HeadingItem(level=tag.name, text=text))
        if len(headings) >= settings.MAX_HEADINGS:
            break
    return headings


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    images: list[str] = []
    for img in soup.find_all("img", src=True):
        src = str(img["src"]).strip()
        if not src or src.startswith("data:"):
            continue
        absolute = urljoin(base_url, src)
        images.append(absolute)
        if len(images) >= 10:  # cap for brevity
            break
    return images


def _count_words(soup: BeautifulSoup) -> int:
    text = soup.get_text(separator=" ", strip=True)
    return len(text.split())


def _detect_language(soup: BeautifulSoup) -> str | None:
    html_tag = soup.find("html")
    if html_tag and isinstance(html_tag, Tag):
        lang = html_tag.get("lang")
        if isinstance(lang, list):
            return lang[0] if lang else None
        return lang
    return None
