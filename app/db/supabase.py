"""
app.db.supabase — All Supabase database operations.

Article status flow:
    PENDING  →  SCRAPED  →  SUMMARISED  →  POSTED
                    ↘            ↘
                    FAILED       FAILED
"""
from supabase import create_client
from datetime import datetime, timedelta, timezone

from app.core.config import SUPABASE_URL, SUPABASE_KEY, BLOCK_BACKOFF_HOURS

# ── Initialise client ──────────────────────────────────────────
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Feed-state helpers ─────────────────────────────────────────
def get_all_feeds():
    """Return every row from feed_state."""
    try:
        res = supabase.table("feed_state").select("*").execute()
        return res.data
    except Exception as e:
        print(f"[DB] ❌ get_all_feeds failed: {e}")
        return []


def get_last_fetched(feed_url):
    """Return the last_fetched_at timestamp for a given feed URL."""
    try:
        res = (
            supabase.table("feed_state")
            .select("last_fetched_at")
            .eq("feed_url", feed_url)
            .execute()
        )
        if res.data:
            return res.data[0]["last_fetched_at"]
        return None
    except Exception as e:
        print(f"[DB] ❌ get_last_fetched failed for {feed_url}: {e}")
        return None


def update_last_fetched(feed_url):
    """Set last_fetched_at to NOW for a feed."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("feed_state").update({
            "last_fetched_at": now,
            "updated_at": now,
        }).eq("feed_url", feed_url).execute()
    except Exception as e:
        print(f"[DB] ❌ update_last_fetched failed for {feed_url}: {e}")


# ── Feed blocking helpers ─────────────────────────────────────
def mark_feed_blocked(feed_url: str, hours: int | None = None):
    """
    Mark a feed as blocked — it will be skipped until `blocked_until` passes.
    Defaults to BLOCK_BACKOFF_HOURS from config.
    """
    try:
        backoff = hours if hours is not None else BLOCK_BACKOFF_HOURS
        blocked_until = datetime.now(timezone.utc) + timedelta(hours=backoff)
        supabase.table("feed_state").update({
            "blocked_until": blocked_until.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("feed_url", feed_url).execute()
        print(f"    🚫 Feed blocked until {blocked_until.isoformat()}: {feed_url}")
    except Exception as e:
        print(f"[DB] ❌ mark_feed_blocked failed for {feed_url}: {e}")


def clear_feed_block(feed_url: str):
    """Remove the block on a feed after a successful scrape."""
    try:
        supabase.table("feed_state").update({
            "blocked_until": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("feed_url", feed_url).execute()
    except Exception as e:
        print(f"[DB] ❌ clear_feed_block failed for {feed_url}: {e}")


def is_feed_blocked(feed_url: str) -> bool:
    """Check if a feed is currently blocked."""
    try:
        res = (
            supabase.table("feed_state")
            .select("blocked_until")
            .eq("feed_url", feed_url)
            .execute()
        )
        if not res.data:
            return False
        blocked_until = res.data[0].get("blocked_until")
        if not blocked_until:
            return False
        dt = datetime.fromisoformat(blocked_until)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < dt
    except Exception as e:
        print(f"[DB] ❌ is_feed_blocked failed for {feed_url}: {e}")
        return False


# ── Article helpers ────────────────────────────────────────────
def article_exists(url):
    """Check if an article URL is already in the database."""
    try:
        res = (
            supabase.table("articles")
            .select("id")
            .eq("url", url)
            .execute()
        )
        return len(res.data) > 0
    except Exception as e:
        print(f"[DB] ❌ article_exists failed for {url}: {e}")
        # Return True to prevent duplicate inserts on DB errors
        return True


def insert_pending_article(title, url, source_feed, published_at=None):
    """Insert a new article with status PENDING. Skips if URL already exists."""
    try:
        if article_exists(url):
            return False

        row = {
            "title": title,
            "url": url,
            "source_feed": source_feed,
            "status": "PENDING",
        }
        if published_at:
            row["published_at"] = published_at

        supabase.table("articles").insert(row).execute()
        return True
    except Exception as e:
        print(f"[DB] ❌ insert_pending_article failed for {url}: {e}")
        return False


def get_pending_articles(limit=1):
    """
    Fetch a batch of PENDING articles, skipping any whose source_feed
    is currently blocked.
    """
    try:
        res = (
            supabase.table("articles")
            .select("*")
            .eq("status", "PENDING")
            .order("created_at")
            .limit(limit)
            .execute()
        )
        # Filter out articles from blocked feeds
        articles = []
        for article in res.data:
            if not is_feed_blocked(article["source_feed"]):
                articles.append(article)
        return articles
    except Exception as e:
        print(f"[DB] ❌ get_pending_articles failed: {e}")
        return []


def mark_article_status(article_id, status, **extra_fields):
    """
    Update an article's status and optionally set extra fields
    (scraped_text, image_url, summary, error_message).

    Valid statuses: PENDING, SCRAPED, SUMMARISED, POSTED, FAILED
    """
    try:
        data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        data.update(extra_fields)
        supabase.table("articles").update(data).eq("id", article_id).execute()
    except Exception as e:
        print(f"[DB] ❌ mark_article_status failed for article {article_id} → {status}: {e}")


# ── Status count helpers (used by AI agent) ────────────────────
def get_status_counts() -> dict:
    """
    Return a dict with the count of articles in each status.
    Example: {"PENDING": 12, "SCRAPED": 3, "SUMMARISED": 5, "POSTED": 40, "FAILED": 2}
    """
    counts = {}
    for status in ("PENDING", "SCRAPED", "SUMMARISED", "POSTED", "FAILED"):
        try:
            res = (
                supabase.table("articles")
                .select("id", count="exact")
                .eq("status", status)
                .execute()
            )
            counts[status] = res.count if res.count is not None else 0
        except Exception as e:
            print(f"[DB] ❌ get_status_counts failed for {status}: {e}")
            counts[status] = 0
    return counts


# ── Agent write helpers ────────────────────────────────────────
def update_articles_status(old_status: str, new_status: str) -> int:
    """
    Bulk-update all articles from `old_status` to `new_status`.
    Returns the number of rows affected.
    """
    try:
        res = (
            supabase.table("articles")
            .update({
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("status", old_status)
            .execute()
        )
        return len(res.data) if res.data else 0
    except Exception as e:
        print(f"[DB] ❌ update_articles_status failed ({old_status} → {new_status}): {e}")
        raise  # Re-raise so the agent tool can report the error


def delete_articles_by_status(status: str) -> int:
    """
    Delete all articles with the given status.
    Returns the number of rows deleted.
    """
    try:
        res = (
            supabase.table("articles")
            .delete()
            .eq("status", status)
            .execute()
        )
        return len(res.data) if res.data else 0
    except Exception as e:
        print(f"[DB] ❌ delete_articles_by_status failed for {status}: {e}")
        raise  # Re-raise so the agent tool can report the error


def get_blocked_feeds() -> list[dict]:
    """
    Return a list of feeds that are currently blocked.
    Each dict has 'feed_url' and 'blocked_until'.
    """
    try:
        res = (
            supabase.table("feed_state")
            .select("feed_url, blocked_until")
            .not_.is_("blocked_until", "null")
            .execute()
        )
        now = datetime.now(timezone.utc)
        blocked = []
        for row in res.data:
            try:
                dt = datetime.fromisoformat(row["blocked_until"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if now < dt:
                    blocked.append(row)
            except Exception:
                continue
        return blocked
    except Exception as e:
        print(f"[DB] ❌ get_blocked_feeds failed: {e}")
        return []
