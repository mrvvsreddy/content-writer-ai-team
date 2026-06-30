"""
app.services.scraper — Scrapes the full text and image from an article URL.

Returns a dict with keys: text, image, blocked.
  - blocked=True means the site is actively refusing requests (403/429/5xx).
"""
import random
import requests
from bs4 import BeautifulSoup
import time

# Rotate User-Agents to reduce fingerprinting
USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
        "Gecko/20100101 Firefox/126.0"
    ),
]

# HTTP status codes that indicate the site is blocking us
BLOCKING_STATUS_CODES = frozenset({403, 429, 503, 520, 521, 522, 523, 524})


def _build_headers() -> dict:
    """Build request headers with a random User-Agent."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
    }


def scrape_article(url: str) -> dict:
    """
    Fetch an article page, extract the main text and an image URL.

    Returns {"text": str, "image": str, "blocked": bool}.
    """
    try:
        print(f"Scraping: {url}")
        # Jittered polite delay (2–4 seconds)
        time.sleep(2 + random.random() * 2)

        response = requests.get(url, headers=_build_headers(), timeout=15)

        # ── Detect blocking ────────────────────────────────────
        if response.status_code in BLOCKING_STATUS_CODES:
            print(f"    ⚠ Blocked (HTTP {response.status_code}): {url}")
            return {"text": "", "image": "", "blocked": True}

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. Extract image
        image_url = ""
        # Try og:image first
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            image_url = og_image["content"]

        # Fallback to the first image in an article tag
        if not image_url:
            article_tag = soup.find("article")
            if article_tag:
                img = article_tag.find("img")
                if img and img.get("src"):
                    image_url = img["src"]

        # 2. Extract text (basic strategy: grab <article> or just paragraphs)
        text_content = ""
        article_body = soup.find("article")

        if article_body:
            paragraphs = article_body.find_all("p")
        else:
            # Look for common main content divs
            main_content = (
                soup.find("main")
                or soup.find(id="main")
                or soup.find(id="content")
            )
            if main_content:
                paragraphs = main_content.find_all("p")
            else:
                # Fallback to all paragraphs in body
                paragraphs = soup.find_all("p")

        text_content = " ".join(
            [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
        )

        # Limit to first 15,000 chars for LLM context
        text_content = text_content[:15000]

        return {"text": text_content, "image": image_url, "blocked": False}

    except requests.exceptions.ConnectionError:
        print(f"    ⚠ Connection refused (likely blocked): {url}")
        return {"text": "", "image": "", "blocked": True}
    except requests.exceptions.Timeout:
        print(f"    ⚠ Timeout (possible blocking): {url}")
        return {"text": "", "image": "", "blocked": True}
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {"text": "", "image": "", "blocked": False}
