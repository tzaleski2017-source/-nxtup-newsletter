-- ============================================================================
-- Twitch Analytics Platform - Streamer Statistics Table
-- ============================================================================
-- Purpose: Pre-computed aggregate metrics for dashboard performance
-- Dependencies: streamers
-- ============================================================================
-- NOTE: This table is populated by batch processes/materialized views, not by
-- direct data collection. Updated daily via analytics pipeline.
-- ============================================================================

CREATE TABLE IF NOT EXISTS streamer_statistics (
    -- Composite primary key (streamer + date)
    streamer_id BIGINT
        REFERENCES streamers(streamer_id) ON DELETE CASCADE,
    calculation_date DATE NOT NULL,

    -- Activity metrics (trailing 30 days)
    total_broadcasts INTEGER DEFAULT 0,         -- Number of streams
    total_streaming_hours NUMERIC(10,2) DEFAULT 0,  -- Total hours streamed
    unique_categories_streamed INTEGER DEFAULT 0,   -- Content diversity

    -- Viewership aggregates
    average_concurrent_viewers NUMERIC(10,2) DEFAULT 0,
    peak_viewers_30d INTEGER DEFAULT 0,         -- Highest peak in period
    median_viewers NUMERIC(10,2) DEFAULT 0,     -- More stable than average

    -- Engagement metrics (KEY FOR HIDDEN GEM DETECTION)
    average_chat_rate NUMERIC(10,4) DEFAULT 0,  -- Messages per viewer per hour
    engagement_consistency NUMERIC(10,4),       -- Std dev of chat rate (lower = more consistent)

    -- Growth indicators
    follower_gain_30d INTEGER DEFAULT 0,        -- Net new followers
    follower_velocity NUMERIC(10,2),            -- Followers per streaming hour
    viewer_growth_rate NUMERIC(8,4),            -- % change in avg viewers vs previous period

    -- Category behavior
    category_switching_frequency NUMERIC(6,2),  -- Average category changes per week
    top_category_id BIGINT
        REFERENCES categories(category_id) ON DELETE SET NULL,
    top_category_percentage NUMERIC(5,2),       -- % of time in top category

    -- Consistency metrics
    streaming_consistency NUMERIC(6,2),         -- Broadcasts per week
    schedule_regularity NUMERIC(4,3),           -- 0-1 score for consistent schedule

    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    PRIMARY KEY (streamer_id, calculation_date),
    CONSTRAINT check_statistics_non_negative
        CHECK (
            total_broadcasts >= 0 AND
            total_streaming_hours >= 0 AND
            unique_categories_streamed >= 0 AND
            average_concurrent_viewers >= 0 AND
            follower_gain_30d >= -999999  -- Can be negative (lost followers)
        )
);

-- ============================================================================
-- Indexes for Analytics Queries
-- ============================================================================

-- Temporal queries (e.g., "stats for all streamers on 2025-10-29")
CREATE INDEX IF NOT EXISTS idx_stats_date
    ON streamer_statistics(calculation_date);

-- Find high-engagement streamers
CREATE INDEX IF NOT EXISTS idx_stats_engagement
    ON streamer_statistics(average_chat_rate)
    WHERE average_chat_rate > 0;

-- Find fast-growing streamers
CREATE INDEX IF NOT EXISTS idx_stats_velocity
    ON streamer_statistics(follower_velocity)
    WHERE follower_velocity > 0;

-- Growth rate analysis
CREATE INDEX IF NOT EXISTS idx_stats_growth_rate
    ON streamer_statistics(viewer_growth_rate)
    WHERE viewer_growth_rate > 0;

-- Multi-category versatility
CREATE INDEX IF NOT EXISTS idx_stats_category_diversity
    ON streamer_statistics(unique_categories_streamed)
    WHERE unique_categories_streamed > 1;

-- Consistent streamers
CREATE INDEX IF NOT EXISTS idx_stats_consistency
    ON streamer_statistics(streaming_consistency)
    WHERE streaming_consistency > 0;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE streamer_statistics IS
    'Pre-computed aggregate metrics updated daily. Optimized for dashboard queries and model features.';

COMMENT ON COLUMN streamer_statistics.calculation_date IS
    'Date these statistics were calculated. Enables historical trending of aggregate metrics.';

COMMENT ON COLUMN streamer_statistics.average_chat_rate IS
    'KEY METRIC: Messages per viewer per hour. High values indicate strong personality-driven engagement.';

COMMENT ON COLUMN streamer_statistics.engagement_consistency IS
    'Standard deviation of chat rate across broadcasts. Lower = more consistent (better).';

COMMENT ON COLUMN streamer_statistics.follower_velocity IS
    'Followers gained per hour streamed. Normalizes for stream frequency.';

COMMENT ON COLUMN streamer_statistics.unique_categories_streamed IS
    'Number of different categories streamed. High values + high engagement = versatile talent.';

COMMENT ON COLUMN streamer_statistics.category_switching_frequency IS
    'Average times per week streamer changes primary category. Helps identify variety streamers.';

COMMENT ON COLUMN streamer_statistics.top_category_percentage IS
    '% of streaming time in most-played category. Low values indicate variety content.';

COMMENT ON COLUMN streamer_statistics.schedule_regularity IS
    'Score 0-1 measuring consistency of streaming schedule. 1 = perfect consistency.';

-- ============================================================================
-- Example Computation Query (Run Daily)
-- ============================================================================

/*
-- This query would be run by a batch job to populate streamer_statistics

INSERT INTO streamer_statistics (
    streamer_id,
    calculation_date,
    total_broadcasts,
    average_chat_rate,
    follower_velocity
    -- ... other fields
)
SELECT
    s.streamer_id,
    CURRENT_DATE as calculation_date,
    COUNT(DISTINCT b.broadcast_id) as total_broadcasts,
    AVG(
        bs.chat_messages_delta::NUMERIC /
        NULLIF(bs.concurrent_viewers, 0) /
        0.25  -- 15 min = 0.25 hours
    ) as average_chat_rate,
    SUM(b.follower_gain)::NUMERIC /
    NULLIF(SUM(b.duration_seconds) / 3600.0, 0) as follower_velocity
FROM streamers s
LEFT JOIN broadcasts b ON s.streamer_id = b.streamer_id
    AND b.started_at > CURRENT_DATE - INTERVAL '30 days'
LEFT JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
GROUP BY s.streamer_id;
*/
