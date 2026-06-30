"""
app.services.image_search — Fetches open-source images based on query.

Strategy:
  1. Prefer the article's own og:image (set by the scraper).
  2. Reject images from known stock-photo domains (Shutterstock, Getty, etc.).
  3. Reject images from editorial sites that burn watermarks into pixels
     (Inc42, Analytics India Mag, YourStory, etc.) — detected by source_feed.
  4. Only search DuckDuckGo as a *fallback* when no usable image exists.
  5. Validate that image URLs actually resolve (HEAD check).
"""
import requests
from ddgs import DDGS
import itertools
import re
from urllib.parse import urlparse


# ── Watermark / stock-photo detection ─────────────────────────
# Domains known to serve watermarked preview images
WATERMARK_DOMAINS = frozenset({
    "shutterstock.com",
    "gettyimages.com",
    "istockphoto.com",
    "depositphotos.com",
    "dreamstime.com",
    "123rf.com",
    "adobestock.com",
    "stock.adobe.com",
    "alamy.com",
    "bigstockphoto.com",
    "canstockphoto.com",
    "stockfresh.com",
    "vectorstock.com",
    "pond5.com",
    "dissolve.com",
    "eyeem.com",
    "stocksy.com",
})

# URL path/query patterns that indicate a watermarked or low-quality preview
WATERMARK_URL_PATTERNS = re.compile(
    r"watermark|wm_|comp_|preview_|thumb_|stock[-_]?photo|"
    r"placeholder|default[-_]?image|no[-_]?image|blank\.png",
    re.IGNORECASE,
)

# ── Editorial watermark detection ─────────────────────────────
# News sites that burn their own logo/watermark into article images.
# These can't be detected from the URL — we identify them by source feed.
# Add/remove domains here as you discover more.
EDITORIAL_WATERMARK_DOMAINS = frozenset({
    "inc42.com",
    "analyticsindiamag.com",
    "yourstory.com",
    "entrackr.com",
    "medianama.com",
})


def _extract_domain(url: str) -> str:
    """Extract the registrable domain from a URL (e.g. 'cdn.inc42.com' → 'inc42.com')."""
    try:
        hostname = urlparse(url).hostname or ""
        # Take the last two parts: 'images.inc42.com' → 'inc42.com'
        parts = hostname.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return hostname
    except Exception:
        return ""


def is_watermarked_image(url: str, source_feed: str = "") -> bool:
    """
    Check if an image should be rejected due to watermarking.

    Catches two types:
      1. Stock-photo domains (Shutterstock, Getty, etc.) — checked via image URL.
      2. Editorial watermarks (Inc42, AIM, etc.) — checked via source_feed URL,
         because these sites serve images from their own domain/CDN so the
         image URL alone looks clean.
    """
    if not url:
        return False

    # ── Type 1: Stock-photo domain check (from image URL) ─────
    try:
        hostname = urlparse(url).hostname or ""
        for domain in WATERMARK_DOMAINS:
            if hostname == domain or hostname.endswith("." + domain):
                return True
    except Exception:
        pass

    # ── Type 2: URL pattern check ─────────────────────────────
    if WATERMARK_URL_PATTERNS.search(url):
        return True

    # ── Type 3: Editorial watermark check (from source_feed) ──
    if source_feed:
        feed_domain = _extract_domain(source_feed)
        if feed_domain in EDITORIAL_WATERMARK_DOMAINS:
            return True

    return False


# ── Image URL validation ──────────────────────────────────────
def is_valid_image_url(url: str) -> bool:
    """
    Verify that a URL points to an actual, loadable, non-watermarked image.
    Checks: starts with http, not from a stock-photo domain, HEAD returns
    200 with an image/* content-type.
    """
    if not url or not url.startswith("http"):
        return False

    # Reject known watermark sources before making a network request
    if is_watermarked_image(url):
        return False

    try:
        resp = requests.head(url, timeout=5, allow_redirects=True)
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("Content-Type", "")
        return content_type.startswith("image/")
    except Exception:
        return False


# ── Search query builder ──────────────────────────────────────
def _build_search_query(title: str) -> str:
    """
    Build a concise image-search query from the article title.
    Strips filler words to get better, more relevant results.
    """
    # Remove common filler/noise words
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "in", "on", "at",
        "to", "for", "of", "by", "its", "how", "what", "why", "when",
        "and", "or", "but", "with", "from", "this", "that", "new",
    }
    words = re.findall(r"[a-zA-Z]+", title.lower())
    keywords = [w for w in words if w not in stop_words]
    # Take up to 5 most meaningful keywords + add "AI illustration"
    query = " ".join(keywords[:5]) + " AI illustration"
    return query


def get_open_source_image(query: str, max_results: int = 5) -> str:
    """
    Search DuckDuckGo for an image related to the query.
    Returns the first *valid, non-watermarked* image URL found.
    Returns empty string if none found or on error.
    """
    search_query = _build_search_query(query)
    try:
        with DDGS() as ddgs:
            results = itertools.islice(ddgs.images(search_query), max_results)
            for result in results:
                image_url = result.get("image")
                if image_url and is_valid_image_url(image_url):
                    return image_url
    except Exception as e:
        print(f"    ⚠️ [Image] DDG search failed for '{search_query}': {e}")
    return ""
