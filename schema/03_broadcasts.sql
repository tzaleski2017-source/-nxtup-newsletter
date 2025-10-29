-- ============================================================================
-- Twitch Analytics Platform - Broadcasts Table
-- ============================================================================
-- Purpose: Individual streaming sessions as primary analytical units
-- Dependencies: streamers, categories
-- ============================================================================

CREATE TABLE IF NOT EXISTS broadcasts (
    -- Primary identifier (auto-incrementing internal ID)
    broadcast_id BIGSERIAL PRIMARY KEY,

    -- Foreign keys
    streamer_id BIGINT NOT NULL
        REFERENCES streamers(streamer_id) ON DELETE CASCADE,
    primary_category_id BIGINT
        REFERENCES categories(category_id) ON DELETE SET NULL,

    -- Broadcast metadata
    stream_title TEXT,                          -- Broadcast title/description
    is_mature BOOLEAN DEFAULT false,            -- Mature content flag

    -- Temporal boundaries
    started_at TIMESTAMPTZ NOT NULL,            -- Stream start time
    ended_at TIMESTAMPTZ,                       -- Stream end time (NULL if ongoing)
    duration_seconds INTEGER,                   -- Computed: ended_at - started_at

    -- Aggregate metrics (computed from broadcast_snapshots)
    average_viewers INTEGER,                    -- Average concurrent viewers
    peak_viewers INTEGER,                       -- Maximum concurrent viewers
    total_chat_messages INTEGER,                -- Total messages across entire stream
    follower_gain INTEGER,                      -- Net new followers during this stream

    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_broadcast_times
        CHECK (ended_at IS NULL OR ended_at > started_at),
    CONSTRAINT check_duration_positive
        CHECK (duration_seconds IS NULL OR duration_seconds > 0),
    CONSTRAINT check_metrics_non_negative
        CHECK (
            (average_viewers IS NULL OR average_viewers >= 0) AND
            (peak_viewers IS NULL OR peak_viewers >= 0) AND
            (total_chat_messages IS NULL OR total_chat_messages >= 0)
        )
);

-- ============================================================================
-- Indexes for Query Optimization
-- ============================================================================

-- Most common: filter by streamer
CREATE INDEX IF NOT EXISTS idx_broadcasts_streamer
    ON broadcasts(streamer_id);

-- Category-level analytics
CREATE INDEX IF NOT EXISTS idx_broadcasts_category
    ON broadcasts(primary_category_id);

-- Temporal queries (e.g., "broadcasts in last 30 days")
CREATE INDEX IF NOT EXISTS idx_broadcasts_started_at
    ON broadcasts(started_at);

-- Composite index for per-streamer historical analysis
CREATE INDEX IF NOT EXISTS idx_broadcasts_streamer_started
    ON broadcasts(streamer_id, started_at);

-- Find currently live streams efficiently
CREATE INDEX IF NOT EXISTS idx_broadcasts_ongoing
    ON broadcasts(ended_at)
    WHERE ended_at IS NULL;

-- Performance analytics (high-performing streams)
CREATE INDEX IF NOT EXISTS idx_broadcasts_peak_viewers
    ON broadcasts(peak_viewers)
    WHERE peak_viewers IS NOT NULL;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE broadcasts IS
    'Individual streaming sessions. Each row represents one stream from start to end.';

COMMENT ON COLUMN broadcasts.broadcast_id IS
    'Auto-incrementing internal identifier for each unique broadcast session.';

COMMENT ON COLUMN broadcasts.primary_category_id IS
    'Main game/category for this stream. Note: streamers can switch mid-stream (tracked in snapshots).';

COMMENT ON COLUMN broadcasts.duration_seconds IS
    'Computed field: ended_at - started_at. NULL for ongoing streams.';

COMMENT ON COLUMN broadcasts.average_viewers IS
    'Computed from broadcast_snapshots. Average concurrent viewers across all snapshots.';

COMMENT ON COLUMN broadcasts.peak_viewers IS
    'Computed from broadcast_snapshots. Maximum concurrent viewers at any point.';

COMMENT ON COLUMN broadcasts.follower_gain IS
    'Net new followers gained during this specific stream. Key metric for stream effectiveness.';

COMMENT ON COLUMN broadcasts.ended_at IS
    'NULL indicates stream is currently live. Set when stream ends.';
