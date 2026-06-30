"""
app.agent.tools — Agent tool definitions for querying the pipeline database.

Each @tool function is a self-contained skill the LangGraph agent can invoke
autonomously based on the user's natural-language request.
"""
from langchain_core.tools import tool

from app.db.supabase import (
    get_status_counts,
    clear_feed_block,
    get_blocked_feeds,
    update_articles_status,
    delete_articles_by_status,
)


# ═══════════════════════════════════════════════════════════════
#  Read Tools
# ═══════════════════════════════════════════════════════════════

@tool
def check_pipeline_status() -> str:
    """
    Check the current status of the news scraper pipeline.
    Returns the number of articles in each status:
    PENDING, SCRAPED, SUMMARISED, POSTED, and FAILED.
    """
    try:
        counts = get_status_counts()
        total = sum(counts.values())
        lines = [
            f"📊 Pipeline Status (Total: {total} articles)",
            f"  ⏳ Pending:     {counts.get('PENDING', 0)}",
            f"  🔄 Scraped:     {counts.get('SCRAPED', 0)}",
            f"  📝 Summarised:  {counts.get('SUMMARISED', 0)}",
            f"  ✅ Posted:      {counts.get('POSTED', 0)}",
            f"  ❌ Failed:      {counts.get('FAILED', 0)}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to fetch pipeline status: {e}"


@tool
def check_pending_count() -> str:
    """
    Check only the number of articles currently waiting to be processed (PENDING).
    """
    try:
        counts = get_status_counts()
        pending = counts.get("PENDING", 0)
        return f"⏳ There are {pending} articles currently pending."
    except Exception as e:
        return f"❌ Failed to fetch pending count: {e}"


@tool
def check_completed_count() -> str:
    """
    Check the number of articles that have been successfully posted.
    """
    try:
        counts = get_status_counts()
        posted = counts.get("POSTED", 0)
        return f"✅ {posted} articles have been successfully posted."
    except Exception as e:
        return f"❌ Failed to fetch completed count: {e}"


@tool
def check_blocked_feeds() -> str:
    """
    List all RSS feeds that are currently blocked due to site-blocking errors.
    Shows which feeds are paused and when they will be unblocked.
    """
    try:
        blocked = get_blocked_feeds()
        if not blocked:
            return "✅ No feeds are currently blocked. All feeds are active."
        lines = [f"🚫 {len(blocked)} feed(s) currently blocked:"]
        for feed in blocked:
            lines.append(f"  • {feed['feed_url']} — until {feed['blocked_until']}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to fetch blocked feeds: {e}"


# ═══════════════════════════════════════════════════════════════
#  Write Tools (Action)
# ═══════════════════════════════════════════════════════════════

@tool
def unblock_feed(feed_url: str) -> str:
    """
    Manually unblock a specific RSS feed so scraping can resume immediately.
    Use this when a feed was blocked by the anti-bot backoff but you know
    the site is accessible again.
    """
    try:
        clear_feed_block(feed_url)
        return f"✅ Feed unblocked: {feed_url}"
    except Exception as e:
        return f"❌ Failed to unblock feed: {e}"


@tool
def retry_failed_articles() -> str:
    """
    Move all FAILED articles back to PENDING so the scraper worker
    will retry them on its next cycle.
    """
    try:
        count = update_articles_status("FAILED", "PENDING")
        if count == 0:
            return "ℹ️ No failed articles to retry."
        return f"♻️ Moved {count} failed article(s) back to PENDING for retry."
    except Exception as e:
        return f"❌ Failed to retry articles: {e}"


@tool
def purge_failed_articles() -> str:
    """
    Permanently delete all FAILED articles from the database.
    Use this to clean up articles that are known to be unscrape-able.
    """
    try:
        count = delete_articles_by_status("FAILED")
        if count == 0:
            return "ℹ️ No failed articles to purge."
        return f"🗑️ Permanently deleted {count} failed article(s)."
    except Exception as e:
        return f"❌ Failed to purge articles: {e}"


@tool
def fetch_open_source_image(query: str) -> str:
    """
    Search for an open-source image using DuckDuckGo Images.
    Use this when you need to find an image related to a topic or replace a watermarked image.
    Returns the image URL if found, otherwise an empty string.
    """
    from app.services.image_search import get_open_source_image
    try:
        image_url = get_open_source_image(query)
        if image_url:
            return f"✅ Found image URL: {image_url}"
        return "❌ No images found for the query."
    except Exception as e:
        return f"❌ Error searching for image: {e}"

