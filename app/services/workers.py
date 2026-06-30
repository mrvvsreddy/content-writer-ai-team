"""
app.services.workers — Background worker loops for RSS polling and article scraping.

Dynamic algorithm:
  • RSS Worker  — polls all feeds every 1 hour (24 scans/day).
                  Only admits articles published on the current UTC date.
                  Uses fast keyword matching for categorization.
  • Scraper Worker — processes exactly 1 PENDING article per cycle,
                     with a 5-minute sleep between each article.
                     If a site blocks, backs off for 1 hour.

These run as asyncio tasks inside the FastAPI lifespan, using asyncio.sleep()
so they don't block the event loop.
"""
import asyncio
import time
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.core.config import (
    AI_KEYWORDS,
    RSS_POLL_INTERVAL_MINUTES,
    SCRAPER_POLL_INTERVAL_MINUTES,
)
from app.db.supabase import (
    get_all_feeds,
    update_last_fetched,
    insert_pending_article,
    get_pending_articles,
    mark_article_status,
    mark_feed_blocked,
    clear_feed_block,
    is_feed_blocked,
)
from app.services.scraper import scrape_article
from app.services.summarizer import generate_summary
from app.services.telegram import send_telegram_message
from app.services.image_search import get_open_source_image


# ═══════════════════════════════════════════════════════════════
#  RSS Worker
# ═══════════════════════════════════════════════════════════════

def is_ai_related(title: str, summary: str) -> bool:
    """Check if the article is AI-related based on keyword matching."""
    text = (title + " " + summary).lower()
    for kw in AI_KEYWORDS:
        if kw == " ai ":
            if " ai " in f" {text} " or " ai," in text or " ai." in text:
                return True
        elif kw in text:
            return True
    return False


def _is_published_today(pub_dt: datetime | None) -> bool:
    """Return True if pub_dt falls on the current UTC date, or if unknown."""
    if pub_dt is None:
        # If we can't determine the date, give it the benefit of the doubt
        return True
    today = datetime.now(timezone.utc).date()
    # Ensure pub_dt is tz-aware for comparison
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    return pub_dt.date() == today


def fetch_and_store_feed(feed_url: str, last_fetched_at: str | None) -> int:
    """
    Parse the RSS feed, filter by keywords AND by today's date,
    then insert new articles as PENDING into Supabase.
    """
    time.sleep(1)  # polite delay

    parsed = feedparser.parse(feed_url)
    new_count = 0

    # Parse the last_fetched_at into a timezone-aware datetime
    cutoff = None
    if last_fetched_at:
        try:
            cutoff = datetime.fromisoformat(last_fetched_at)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
        except Exception:
            cutoff = None

    for entry in parsed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        summary = entry.get("summary", "")
        pub_str = entry.get("published", "")

        # Try to parse the published date
        pub_dt = None
        if pub_str:
            try:
                pub_dt = parsedate_to_datetime(pub_str)
            except Exception:
                pass

        # ── Filter 1: Skip articles older than our cutoff ─────
        if cutoff and pub_dt and pub_dt <= cutoff:
            continue

        # ── Filter 2: Only admit articles published today ─────
        if not _is_published_today(pub_dt):
            continue

        # ── Filter 3: Keyword filter ─────────────────────────
        if not is_ai_related(title, summary):
            continue

        # Insert into Supabase
        published_iso = pub_dt.isoformat() if pub_dt else None
        inserted = insert_pending_article(title, link, feed_url, published_iso)
        if inserted:
            new_count += 1

    return new_count


def poll_all_feeds():
    """One cycle: poll every feed in feed_state and insert new PENDING articles."""
    print(
        f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"RSS Worker — polling feeds..."
    )
    feeds = get_all_feeds()
    total_new = 0

    for feed in feeds:
        feed_url = feed["feed_url"]
        last_fetched = feed.get("last_fetched_at")

        # Skip feeds that are currently blocked
        if is_feed_blocked(feed_url):
            print(f"  ⏸ Skipping (blocked): {feed_url}")
            continue

        print(f"  Fetching: {feed_url}")

        try:
            count = fetch_and_store_feed(feed_url, last_fetched)
            total_new += count
            update_last_fetched(feed_url)
        except Exception as e:
            print(f"  ERROR on {feed_url}: {e}")

    print(f"RSS Worker — inserted {total_new} new PENDING articles (today only).")


async def rss_worker():
    """Async loop that polls RSS feeds every RSS_POLL_INTERVAL_MINUTES (1 hour)."""
    delay_seconds = RSS_POLL_INTERVAL_MINUTES * 60
    print(
        f"[RSS Worker] Started — polling every {RSS_POLL_INTERVAL_MINUTES} minutes "
        f"({24 * 60 // RSS_POLL_INTERVAL_MINUTES} scans/day)"
    )
    while True:
        try:
            # Run the synchronous polling in a thread so we don't block the loop
            await asyncio.to_thread(poll_all_feeds)
        except Exception as e:
            print(f"[RSS Worker] Unhandled error: {e}")
        print(
            f"[RSS Worker] Sleeping for {RSS_POLL_INTERVAL_MINUTES} minutes..."
        )
        await asyncio.sleep(delay_seconds)


# ═══════════════════════════════════════════════════════════════
#  Scraper + Summarizer Worker
# ═══════════════════════════════════════════════════════════════

SUMMARY_FAIL_MESSAGES = frozenset({
    "Summary generation failed.",
    "Not enough text to summarize.",
    "No OpenRouter API key provided.",
})


def process_article(article: dict) -> str:
    """
    Scrape an article's text, generate a summary, and update its status
    through the pipeline: PENDING → SCRAPED → SUMMARISED (or FAILED).

    Returns:
        "ok"      — article fully processed
        "blocked" — site is blocking, caller should back off
        "failed"  — scrape/summary failed but site is not blocking
    """
    article_id = article["id"]
    url = article["url"]
    title = article["title"]
    source_feed = article["source_feed"]

    print(f"  🔍 [Scraper] Scraping: {title}")

    # ── Step 1: Scrape ────────────────────────────────────────
    scraped = scrape_article(url)

    # Handle site blocking
    if scraped.get("blocked"):
        print(f"    🚫 Site is blocking — marking feed for 1hr backoff")
        mark_feed_blocked(source_feed)
        # Leave article as PENDING so it can be retried later
        return "blocked"

    if not scraped["text"]:
        print(f"    ❌ [Scraper] Failed to scrape text.")
        mark_article_status(
            article_id,
            "FAILED",
            error_message="Could not extract article text",
            image_url=scraped.get("image", ""),
        )
        return "failed"
        
    # ── Image handling: validate existing, fallback to DDG search ──
    from app.services.image_search import is_valid_image_url

    original_image = scraped.get("image", "")

    if original_image and is_valid_image_url(original_image):
        # The article's own og:image is valid — keep it
        print(f"    🖼️ [Image] Using article's own image (valid)")
    else:
        # No image or broken URL — try DDG as fallback
        print(f"    🖼️ [Image] No valid article image — searching DDG fallback...")
        fallback_image = get_open_source_image(title)
        if fallback_image:
            scraped["image"] = fallback_image
            print(f"    ✅ [Image] Found fallback image from DDG")
        else:
            scraped["image"] = ""
            print(f"    ⚠️ [Image] No image found — posting without image")

    # Mark as SCRAPED
    mark_article_status(
        article_id,
        "SCRAPED",
        scraped_text=scraped["text"],
        image_url=scraped.get("image", ""),
    )
    print(f"    ✅ [Scraper] Scraped — {len(scraped['text'])} chars")

    # On a successful scrape, clear any previous block on this feed
    clear_feed_block(source_feed)

    print(f"    🤖 [Summarizer] Summarizing article...")
    summary, tokens_used = generate_summary(scraped["text"], title)

    if not summary or summary in SUMMARY_FAIL_MESSAGES:
        print(f"    ❌ [Summarizer] Summary failed: {summary}")
        mark_article_status(
            article_id,
            "FAILED",
            error_message=f"Summary failed: {summary}",
        )
        return "failed"

    # Mark as SUMMARISED
    mark_article_status(
        article_id,
        "SUMMARISED",
        summary=summary,
    )
    print(f"    ✅ [Summarizer] Summarised")

    # ── Step 3: Send to Telegram ──────────────────────────────
    print(f"    ✈️ [Telegram] Sending to Telegram channel...")
    sent = send_telegram_message(
        title=title, 
        summary=summary, 
        article_url=url, 
        image_url=scraped.get("image"),
        target="channel"
    )

    if sent:
        mark_article_status(article_id, "POSTED")
        print(f"    ✅ [Telegram] Posted to channel")
    else:
        print(f"    ⚠ Failed to post to channel (left as SUMMARISED)")

    print(f"    ✈️ [Telegram] Sending to Telegram admin DM...")
    admin_summary = f"{summary}\n\n🤖 Tokens used: {tokens_used}"
    sent_admin = send_telegram_message(
        title=title, 
        summary=admin_summary, 
        article_url=url, 
        image_url=scraped.get("image"),
        target="admin"
    )
    
    if sent_admin:
        print(f"    ✅ [Telegram] Posted to admin DM")
    else:
        print(f"    ⚠ Failed to post to admin DM")

    return "ok"


async def scraper_worker():
    """
    Async loop that processes exactly 1 PENDING article per cycle,
    with a 5-minute gap between each article.

    If a site blocks, the feed is marked as blocked for 1 hour
    and the article is left as PENDING for retry.
    """
    delay_seconds = SCRAPER_POLL_INTERVAL_MINUTES * 60
    print(
        f"[Scraper Worker] Started — processing 1 article every "
        f"{SCRAPER_POLL_INTERVAL_MINUTES} minutes"
    )
    while True:
        try:
            # Fetch exactly 1 pending article (skipping blocked feeds)
            articles = await asyncio.to_thread(get_pending_articles, 1)

            if articles:
                result = await asyncio.to_thread(process_article, articles[0])
                if result == "ok":
                    print(f"[Scraper Worker] ✅ Article processed successfully.")
                elif result == "blocked":
                    print(f"[Scraper Worker] ⏸ Site blocked — will retry in 1 hour.")
                else:
                    print(f"[Scraper Worker] ❌ Article processing failed.")
            else:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"[Scraper Worker] No pending articles to process."
                )
        except Exception as e:
            print(f"[Scraper Worker] Unhandled error: {e}")

        print(
            f"[Scraper Worker] Sleeping for {SCRAPER_POLL_INTERVAL_MINUTES} minutes..."
        )
        await asyncio.sleep(delay_seconds)
