"""
app.services.image_search — Fetches open-source images based on query.

Strategy:
  1. Prefer the article's own og:image (set by the scraper).
  2. Only search DuckDuckGo as a *fallback* when no og:image exists.
  3. Validate that image URLs actually resolve (HEAD check).
"""
import requests
from ddgs import DDGS
import itertools
import re


# ── Image URL validation ──────────────────────────────────────
def is_valid_image_url(url: str) -> bool:
    """
    Verify that a URL points to an actual, loadable image.
    Uses a lightweight HEAD request to check status and content-type.
    """
    if not url or not url.startswith("http"):
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


def get_open_source_image(query: str, max_results: int = 3) -> str:
    """
    Search DuckDuckGo for an image related to the query.
    Returns the first *valid* image URL found (verified by HEAD request).
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
