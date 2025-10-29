-- ============================================================================
-- Twitch Analytics Platform - Example Analytical Queries
-- ============================================================================
-- Purpose: Demonstrate the analytical capabilities enabled by the schema
-- Usage: Run after inserting sample data (docs/sample_data.sql)
-- ============================================================================

\echo '============================================================================'
\echo 'Example Analytical Queries for Hidden Gem Detection'
\echo '============================================================================'
\echo ''

-- ============================================================================
-- QUERY 1: Identify High-Engagement Streamers
-- ============================================================================
-- Purpose: Find streamers with chat engagement above threshold
-- Key Metric: chat_messages_delta per viewer (engagement rate)

\echo '>>> Query 1: High-Engagement Streamers (Last 30 Days)'
\echo ''

SELECT
    s.username,
    s.display_name,
    COUNT(DISTINCT b.broadcast_id) as total_broadcasts,
    COUNT(DISTINCT b.primary_category_id) as categories_played,
    ROUND(AVG(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)), 3) as avg_engagement_rate,
    ROUND(STDDEV(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)), 3) as engagement_consistency,
    ROUND(AVG(bs.concurrent_viewers)::NUMERIC, 0) as avg_viewers
FROM streamers s
JOIN broadcasts b ON s.streamer_id = b.streamer_id
JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
WHERE b.started_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY s.streamer_id, s.username, s.display_name
HAVING AVG(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)) > 5.0
ORDER BY avg_engagement_rate DESC;

\echo ''

-- ============================================================================
-- QUERY 2: Category-Independent Performance (Hidden Gem Indicator)
-- ============================================================================
-- Purpose: Identify streamers who maintain engagement across categories
-- This is THE KEY QUERY for distinguishing personality vs game-hype

\echo '>>> Query 2: Category-Independent Performers (Versatility Test)'
\echo ''

WITH category_performance AS (
    SELECT
        s.streamer_id,
        s.username,
        c.category_name,
        AVG(bs.concurrent_viewers) as avg_viewers_in_category,
        AVG(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)) as avg_engagement_in_category,
        COUNT(DISTINCT b.broadcast_id) as broadcasts_in_category
    FROM streamers s
    JOIN broadcasts b ON s.streamer_id = b.streamer_id
    JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
    JOIN categories c ON bs.category_id = c.category_id
    WHERE b.started_at > CURRENT_DATE - INTERVAL '60 days'
    GROUP BY s.streamer_id, s.username, c.category_name
)
SELECT
    username,
    COUNT(DISTINCT category_name) as categories_count,
    ROUND(AVG(avg_engagement_in_category), 3) as overall_avg_engagement,
    ROUND(STDDEV(avg_engagement_in_category), 3) as engagement_variance,
    ROUND(MIN(avg_engagement_in_category), 3) as min_category_engagement,
    ROUND(MAX(avg_engagement_in_category), 3) as max_category_engagement,
    -- Low variance = consistent across categories = personality-driven
    CASE
        WHEN STDDEV(avg_engagement_in_category) < 0.5 THEN 'HIGHLY VERSATILE'
        WHEN STDDEV(avg_engagement_in_category) < 1.0 THEN 'VERSATILE'
        ELSE 'GAME-DEPENDENT'
    END as versatility_rating
FROM category_performance
WHERE broadcasts_in_category >= 2  -- Must have at least 2 broadcasts per category
GROUP BY username, streamer_id
HAVING COUNT(DISTINCT category_name) >= 2  -- Must stream multiple categories
ORDER BY engagement_variance ASC, overall_avg_engagement DESC;

\echo ''

-- ============================================================================
-- QUERY 3: Game-Hype Detection
-- ============================================================================
-- Purpose: Identify streamers whose success is tied to trending games

\echo '>>> Query 3: Game-Hype Dependency Analysis'
\echo ''

SELECT
    s.username,
    c.category_name,
    c.is_trending,
    COUNT(b.broadcast_id) as broadcasts_count,
    ROUND(AVG(bs.concurrent_viewers)::NUMERIC, 0) as avg_viewers,
    ROUND(AVG(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)), 3) as engagement_rate,
    SUM(b.follower_gain) as total_followers_gained
FROM streamers s
JOIN broadcasts b ON s.streamer_id = b.streamer_id
JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
JOIN categories c ON bs.category_id = c.category_id
GROUP BY s.streamer_id, s.username, c.category_id, c.category_name, c.is_trending
ORDER BY s.username, c.is_trending DESC, avg_viewers DESC;

\echo ''

-- ============================================================================
-- QUERY 4: Follower Velocity (Growth Rate per Hour Streamed)
-- ============================================================================
-- Purpose: Normalize follower growth by streaming hours to find efficient growers

\echo '>>> Query 4: Follower Velocity Analysis'
\echo ''

SELECT
    s.username,
    SUM(b.follower_gain) as total_follower_gain,
    ROUND(SUM(b.duration_seconds) / 3600.0, 1) as total_hours_streamed,
    ROUND(SUM(b.follower_gain)::NUMERIC / NULLIF(SUM(b.duration_seconds) / 3600.0, 0), 2) as follower_velocity,
    ROUND(AVG(bs.concurrent_viewers)::NUMERIC, 0) as avg_viewers,
    -- Efficiency score: followers per hour per 100 viewers
    ROUND(
        (SUM(b.follower_gain)::NUMERIC / NULLIF(SUM(b.duration_seconds) / 3600.0, 0)) /
        NULLIF(AVG(bs.concurrent_viewers), 0) * 100,
        3
    ) as efficiency_score
FROM streamers s
JOIN broadcasts b ON s.streamer_id = b.streamer_id
JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
WHERE b.started_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY s.streamer_id, s.username
ORDER BY follower_velocity DESC;

\echo ''

-- ============================================================================
-- QUERY 5: Hidden Gem Composite Score
-- ============================================================================
-- Purpose: Combine multiple signals into a single "hidden gem" ranking

\echo '>>> Query 5: Hidden Gem Composite Ranking'
\echo ''

WITH streamer_metrics AS (
    SELECT
        s.streamer_id,
        s.username,
        s.display_name,
        -- Engagement metric
        AVG(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)) as avg_engagement_rate,
        STDDEV(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)) as engagement_std_dev,
        -- Growth metric
        SUM(b.follower_gain)::NUMERIC / NULLIF(SUM(b.duration_seconds) / 3600.0, 0) as follower_velocity,
        -- Versatility metric
        COUNT(DISTINCT b.primary_category_id) as unique_categories,
        -- Size metric (we want SMALL streamers, so inverse this)
        AVG(bs.concurrent_viewers) as avg_viewers
    FROM streamers s
    JOIN broadcasts b ON s.streamer_id = b.streamer_id
    JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
    WHERE b.started_at > CURRENT_DATE - INTERVAL '30 days'
    GROUP BY s.streamer_id, s.username, s.display_name
)
SELECT
    username,
    display_name,
    ROUND(avg_engagement_rate, 3) as engagement_rate,
    ROUND(engagement_std_dev, 3) as engagement_consistency,
    ROUND(follower_velocity, 2) as follower_velocity,
    unique_categories,
    ROUND(avg_viewers::NUMERIC, 0) as avg_viewers,
    -- Composite score (higher = better hidden gem)
    ROUND(
        (avg_engagement_rate * 20) +                    -- High engagement (weight: 20)
        (follower_velocity * 10) +                      -- Growth rate (weight: 10)
        (unique_categories * 15) +                      -- Versatility (weight: 15)
        (CASE WHEN engagement_std_dev < 1 THEN 20 ELSE 0 END) +  -- Consistency bonus
        (CASE WHEN avg_viewers < 200 THEN 30 ELSE 0 END) +  -- Undiscovered bonus
        (CASE WHEN avg_viewers > 1000 THEN -50 ELSE 0 END)  -- Penalty for already popular
    , 2) as hidden_gem_score
FROM streamer_metrics
ORDER BY hidden_gem_score DESC
LIMIT 10;

\echo ''

-- ============================================================================
-- QUERY 6: Time-Series Viewer Retention Analysis
-- ============================================================================
-- Purpose: Analyze how viewership evolves during a stream (retention curve)

\echo '>>> Query 6: Stream Retention Pattern (Sample Broadcast)'
\echo ''

SELECT
    bs.snapshot_timestamp,
    ROUND(bs.stream_uptime_seconds / 3600.0, 2) as hours_into_stream,
    bs.concurrent_viewers,
    bs.chat_messages_delta,
    ROUND(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0), 3) as engagement_rate,
    bs.follower_count,
    bs.follower_count - LAG(bs.follower_count) OVER (ORDER BY bs.snapshot_timestamp) as follower_gain_delta
FROM broadcast_snapshots bs
WHERE bs.broadcast_id = 1  -- Alice's first broadcast
ORDER BY bs.snapshot_timestamp;

\echo ''

-- ============================================================================
-- QUERY 7: Category Switching Impact
-- ============================================================================
-- Purpose: Measure performance change when streamers switch categories

\echo '>>> Query 7: Category Switching Impact Analysis'
\echo ''

WITH category_switches AS (
    SELECT
        bs.broadcast_id,
        bs.snapshot_timestamp,
        bs.category_id,
        LAG(bs.category_id) OVER (PARTITION BY bs.broadcast_id ORDER BY bs.snapshot_timestamp) as prev_category_id,
        bs.concurrent_viewers,
        LAG(bs.concurrent_viewers) OVER (PARTITION BY bs.broadcast_id ORDER BY bs.snapshot_timestamp) as prev_viewers,
        bs.chat_messages_delta
    FROM broadcast_snapshots bs
)
SELECT
    b.streamer_id,
    s.username,
    c1.category_name as from_category,
    c2.category_name as to_category,
    cs.prev_viewers as viewers_before_switch,
    cs.concurrent_viewers as viewers_after_switch,
    cs.concurrent_viewers - cs.prev_viewers as viewer_change,
    ROUND((cs.concurrent_viewers - cs.prev_viewers)::NUMERIC / NULLIF(cs.prev_viewers, 0) * 100, 1) as percent_change
FROM category_switches cs
JOIN broadcasts b ON cs.broadcast_id = b.broadcast_id
JOIN streamers s ON b.streamer_id = s.streamer_id
JOIN categories c1 ON cs.prev_category_id = c1.category_id
JOIN categories c2 ON cs.category_id = c2.category_id
WHERE cs.category_id != cs.prev_category_id  -- Only switches
ORDER BY viewer_change DESC;

\echo ''
\echo '============================================================================'
\echo 'Query Examples Complete!'
\echo '============================================================================'
\echo ''
\echo 'These queries demonstrate:'
\echo '  1. Engagement rate calculation (chat per viewer)'
\echo '  2. Category-independent performance analysis'
\echo '  3. Game-hype dependency detection'
\echo '  4. Growth efficiency (follower velocity)'
\echo '  5. Composite scoring for hidden gem ranking'
\echo '  6. Time-series retention analysis'
\echo '  7. Category switching impact measurement'
\echo ''
\echo 'All metrics support the goal of identifying personality-driven streamers'
\echo 'who can maintain engagement across different content categories.'
\echo '============================================================================'
