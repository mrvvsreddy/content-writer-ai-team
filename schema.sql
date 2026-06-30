-- ============================================================
-- AI News Aggregator — Supabase Schema
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard)
-- ============================================================

-- 1. feed_state: tracks the last time each RSS feed was polled
CREATE TABLE IF NOT EXISTS feed_state (
    id          BIGSERIAL PRIMARY KEY,
    feed_url    TEXT UNIQUE NOT NULL,
    feed_type   TEXT NOT NULL DEFAULT 'blog',
    last_fetched_at TIMESTAMPTZ DEFAULT '1970-01-01T00:00:00Z',
    blocked_until   TIMESTAMPTZ,          -- NULL = not blocked; set when a site blocks us
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. articles: stores every discovered article and its processing status
CREATE TABLE IF NOT EXISTS articles (
    id              BIGSERIAL PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    source_feed     TEXT NOT NULL,
    published_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'SCRAPED', 'SUMMARISED', 'POSTED', 'FAILED')),
    scraped_text    TEXT,
    image_url       TEXT,
    summary         TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles (status);
CREATE INDEX IF NOT EXISTS idx_articles_url    ON articles (url);
CREATE INDEX IF NOT EXISTS idx_feed_state_url  ON feed_state (feed_url);

-- 3. Seed the feed_state table with initial feeds so the workers know what to poll
INSERT INTO feed_state (feed_url, feed_type) VALUES
    ('https://techcrunch.com/feed/', 'blog'),
    ('https://analyticsindiamag.com/feed/', 'blog'),
    ('https://inc42.com/feed', 'blog'),
    ('https://yourstory.com/feed', 'blog'),
    ('https://pandaily.com/feed', 'blog'),
    ('http://export.arxiv.org/rss/cs.AI', 'academic'),
    ('https://news.ycombinator.com/rss', 'aggregator')
ON CONFLICT (feed_url) DO NOTHING;
