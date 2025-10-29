-- ============================================================================
-- Twitch Analytics Platform - Streamers Table
-- ============================================================================
-- Purpose: Master entity table for all tracked Twitch streamers
-- Dependencies: None (base table)
-- ============================================================================

CREATE TABLE IF NOT EXISTS streamers (
    -- Primary identifier (Twitch's immutable user ID)
    streamer_id BIGINT PRIMARY KEY,

    -- Profile information
    username VARCHAR(25) NOT NULL,              -- Current Twitch username (mutable)
    display_name VARCHAR(25),                   -- Display name with capitalization
    profile_image_url TEXT,                     -- Avatar URL
    description TEXT,                           -- Channel description
    broadcaster_language VARCHAR(10),           -- Stream language (e.g., 'en', 'es')

    -- Temporal tracking
    account_created_at TIMESTAMPTZ,             -- When Twitch account was created
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- When we started tracking
    last_seen_at TIMESTAMPTZ,                   -- Most recent streaming activity

    -- Status management
    is_active BOOLEAN DEFAULT true,             -- Flag for active tracking

    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes for Query Optimization
-- ============================================================================

-- Username lookup (case-sensitive)
CREATE INDEX IF NOT EXISTS idx_streamers_username
    ON streamers(username);

-- Temporal queries (e.g., "streamers discovered in last 30 days")
CREATE INDEX IF NOT EXISTS idx_streamers_discovered_at
    ON streamers(discovered_at);

-- Filter active streamers efficiently
CREATE INDEX IF NOT EXISTS idx_streamers_active
    ON streamers(is_active)
    WHERE is_active = true;

-- Language-based filtering
CREATE INDEX IF NOT EXISTS idx_streamers_language
    ON streamers(broadcaster_language)
    WHERE broadcaster_language IS NOT NULL;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE streamers IS
    'Master table for all tracked Twitch streamers. Stores static profile information and tracking metadata.';

COMMENT ON COLUMN streamers.streamer_id IS
    'Twitch user ID (immutable). This is the authoritative identifier even if username changes.';

COMMENT ON COLUMN streamers.username IS
    'Current Twitch username. Can change over time, so always use streamer_id for joins.';

COMMENT ON COLUMN streamers.discovered_at IS
    'Timestamp when we first added this streamer to our tracking system.';

COMMENT ON COLUMN streamers.last_seen_at IS
    'Most recent broadcast or activity. Used to identify inactive accounts.';

COMMENT ON COLUMN streamers.is_active IS
    'Soft-delete flag. Set to false to stop tracking without losing historical data.';
