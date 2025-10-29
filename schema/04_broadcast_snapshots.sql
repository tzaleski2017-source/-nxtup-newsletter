-- ============================================================================
-- Twitch Analytics Platform - Broadcast Snapshots Table
-- ============================================================================
-- Purpose: High-frequency time-series data - the heart of engagement analytics
-- Dependencies: broadcasts, streamers, categories
-- ============================================================================
-- CRITICAL: This table will grow rapidly (e.g., 4 snapshots/hour * 8 hours * 1000
-- streamers = 32K rows/day). Consider partitioning by snapshot_timestamp monthly.
-- ============================================================================

CREATE TABLE IF NOT EXISTS broadcast_snapshots (
    -- Primary identifier
    snapshot_id BIGSERIAL PRIMARY KEY,

    -- Foreign keys (denormalized for performance)
    broadcast_id BIGINT NOT NULL
        REFERENCES broadcasts(broadcast_id) ON DELETE CASCADE,
    streamer_id BIGINT NOT NULL
        REFERENCES streamers(streamer_id) ON DELETE CASCADE,
    category_id BIGINT
        REFERENCES categories(category_id) ON DELETE SET NULL,

    -- Snapshot timestamp
    snapshot_timestamp TIMESTAMPTZ NOT NULL,

    -- Viewership metrics
    concurrent_viewers INTEGER NOT NULL
        CHECK (concurrent_viewers >= 0),        -- Viewers at this exact moment

    -- Follower metrics (absolute counts)
    follower_count BIGINT NOT NULL
        CHECK (follower_count >= 0),            -- Total followers at this moment

    -- Engagement metrics (incremental)
    chat_messages_delta INTEGER NOT NULL DEFAULT 0
        CHECK (chat_messages_delta >= 0),       -- New messages since last snapshot

    -- Stream health indicators
    stream_uptime_seconds INTEGER,              -- Seconds since stream started
    viewer_rank INTEGER,                        -- Rank on Twitch at this moment

    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_broadcast_snapshot
        UNIQUE (broadcast_id, snapshot_timestamp)
);

-- ============================================================================
-- Indexes for Time-Series Analytics
-- ============================================================================

-- Most common: snapshots for a specific broadcast
CREATE INDEX IF NOT EXISTS idx_snapshots_broadcast
    ON broadcast_snapshots(broadcast_id);

-- Streamer-level time-series (bypassing broadcasts join)
CREATE INDEX IF NOT EXISTS idx_snapshots_streamer
    ON broadcast_snapshots(streamer_id);

-- Category-level performance analysis
CREATE INDEX IF NOT EXISTS idx_snapshots_category
    ON broadcast_snapshots(category_id);

-- Temporal queries (e.g., "all snapshots in last week")
CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
    ON broadcast_snapshots(snapshot_timestamp);

-- Composite: streamer performance over time
CREATE INDEX IF NOT EXISTS idx_snapshots_streamer_time
    ON broadcast_snapshots(streamer_id, snapshot_timestamp);

-- Composite: broadcast time-series (ordered)
CREATE INDEX IF NOT EXISTS idx_snapshots_broadcast_time
    ON broadcast_snapshots(broadcast_id, snapshot_timestamp);

-- High-engagement moments (for highlight detection)
CREATE INDEX IF NOT EXISTS idx_snapshots_high_engagement
    ON broadcast_snapshots(chat_messages_delta)
    WHERE chat_messages_delta > 100;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE broadcast_snapshots IS
    'Time-series snapshots captured every 15 minutes during broadcasts. Core table for engagement analytics.';

COMMENT ON COLUMN broadcast_snapshots.streamer_id IS
    'Denormalized from broadcasts for direct querying. Enables faster time-series analysis without joins.';

COMMENT ON COLUMN broadcast_snapshots.category_id IS
    'Category at this specific moment. May differ from broadcast.primary_category_id if streamer switched games.';

COMMENT ON COLUMN broadcast_snapshots.concurrent_viewers IS
    'Viewer count at this exact snapshot moment. Not average - use for calculating trends.';

COMMENT ON COLUMN broadcast_snapshots.follower_count IS
    'Absolute cumulative follower count. Subtract previous snapshot to get follower velocity.';

COMMENT ON COLUMN broadcast_snapshots.chat_messages_delta IS
    'NEW messages since last snapshot. Divide by concurrent_viewers and time interval for engagement rate.';

COMMENT ON COLUMN broadcast_snapshots.stream_uptime_seconds IS
    'Seconds since stream started. Useful for analyzing viewer retention curves.';

COMMENT ON COLUMN broadcast_snapshots.viewer_rank IS
    'Rank on Twitch at this moment (1 = most viewed). Useful for identifying breakout moments.';

-- ============================================================================
-- Performance Considerations
-- ============================================================================

-- For production: Consider table partitioning
-- CREATE TABLE broadcast_snapshots_2025_10 PARTITION OF broadcast_snapshots
--     FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

-- For archival: Move old data to separate table after 1 year
-- CREATE TABLE broadcast_snapshots_archive (LIKE broadcast_snapshots INCLUDING ALL);
