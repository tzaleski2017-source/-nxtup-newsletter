-- ============================================================================
-- Twitch Analytics Platform - Sample Data for Testing
-- ============================================================================
-- Purpose: Insert representative sample data for schema validation
-- Usage: Execute after running schema/setup.sql
-- ============================================================================

-- Disable triggers during bulk insert (optional, for performance)
BEGIN;

\echo '============================================================================'
\echo 'Inserting Sample Data'
\echo '============================================================================'

-- ============================================================================
-- Sample Streamers
-- ============================================================================

INSERT INTO streamers (
    streamer_id,
    username,
    display_name,
    account_created_at,
    discovered_at,
    broadcaster_language,
    description,
    is_active
) VALUES
    (1001, 'hidden_gem_alice', 'HiddenGemAlice', '2023-01-15 10:00:00+00', '2025-10-01 12:00:00+00', 'en', 'Variety streamer with high engagement', true),
    (1002, 'rising_bob', 'RisingBob', '2022-06-20 14:30:00+00', '2025-10-05 09:15:00+00', 'en', 'Focused on personality-driven content', true),
    (1003, 'hype_hunter_carol', 'HypeHunterCarol', '2024-03-10 08:00:00+00', '2025-10-10 16:45:00+00', 'en', 'Plays trending games exclusively', true),
    (1004, 'consistent_dave', 'ConsistentDave', '2021-11-05 11:20:00+00', '2025-09-15 10:00:00+00', 'en', 'Streams daily with loyal community', true),
    (1005, 'versatile_eve', 'VersatileEve', '2023-08-22 13:00:00+00', '2025-10-12 14:30:00+00', 'es', 'Multi-category streamer', true);

\echo '✓ Inserted 5 sample streamers'

-- ============================================================================
-- Sample Categories
-- ============================================================================

INSERT INTO categories (
    category_id,
    category_name,
    category_type,
    is_trending,
    first_seen_at
) VALUES
    (2001, 'League of Legends', 'game', false, '2025-09-01 00:00:00+00'),
    (2002, 'Just Chatting', 'creative', false, '2025-09-01 00:00:00+00'),
    (2003, 'Valorant', 'game', true, '2025-09-15 00:00:00+00'),
    (2004, 'Minecraft', 'game', false, '2025-09-01 00:00:00+00'),
    (2005, 'Super Hyped New Game', 'game', true, '2025-10-20 00:00:00+00'),
    (2006, 'Art', 'creative', false, '2025-09-01 00:00:00+00');

\echo '✓ Inserted 6 sample categories'

-- ============================================================================
-- Sample Broadcasts
-- ============================================================================

-- Alice's broadcasts (versatile, high engagement across categories)
INSERT INTO broadcasts (
    streamer_id,
    primary_category_id,
    stream_title,
    started_at,
    ended_at,
    duration_seconds,
    average_viewers,
    peak_viewers,
    total_chat_messages,
    follower_gain
) VALUES
    (1001, 2001, 'Climbing the ranks!', '2025-10-20 14:00:00+00', '2025-10-20 18:00:00+00', 14400, 150, 220, 8500, 45),
    (1001, 2002, 'Just vibing and chatting', '2025-10-22 16:00:00+00', '2025-10-22 19:30:00+00', 12600, 180, 250, 12000, 62),
    (1001, 2004, 'Building a community server', '2025-10-24 15:00:00+00', '2025-10-24 20:00:00+00', 18000, 165, 210, 9800, 51);

-- Bob's broadcasts (consistent personality-driven)
INSERT INTO broadcasts (
    streamer_id,
    primary_category_id,
    stream_title,
    started_at,
    ended_at,
    duration_seconds,
    average_viewers,
    peak_viewers,
    total_chat_messages,
    follower_gain
) VALUES
    (1002, 2002, 'Story time and Q&A', '2025-10-21 12:00:00+00', '2025-10-21 16:00:00+00', 14400, 200, 280, 15000, 78),
    (1002, 2002, 'Community game night', '2025-10-23 13:00:00+00', '2025-10-23 17:30:00+00', 16200, 210, 295, 16500, 85);

-- Carol's broadcasts (game-hype dependent)
INSERT INTO broadcasts (
    streamer_id,
    primary_category_id,
    stream_title,
    started_at,
    ended_at,
    duration_seconds,
    average_viewers,
    peak_viewers,
    total_chat_messages,
    follower_gain
) VALUES
    (1003, 2005, 'NEW GAME HYPE!!!', '2025-10-25 10:00:00+00', '2025-10-25 15:00:00+00', 18000, 850, 1200, 12000, 320),
    (1003, 2001, 'Trying League...', '2025-10-26 11:00:00+00', '2025-10-26 13:00:00+00', 7200, 45, 60, 800, 5);

-- Dave's broadcast (consistent, loyal audience)
INSERT INTO broadcasts (
    streamer_id,
    primary_category_id,
    stream_title,
    started_at,
    ended_at,
    duration_seconds,
    average_viewers,
    peak_viewers,
    total_chat_messages,
    follower_gain
) VALUES
    (1004, 2001, 'Daily League grind', '2025-10-27 18:00:00+00', '2025-10-27 22:00:00+00', 14400, 95, 110, 7500, 12);

\echo '✓ Inserted 8 sample broadcasts'

-- ============================================================================
-- Sample Broadcast Snapshots (Alice's first broadcast)
-- ============================================================================
-- Simulating snapshots every 30 minutes for one broadcast

INSERT INTO broadcast_snapshots (
    broadcast_id,
    streamer_id,
    category_id,
    snapshot_timestamp,
    concurrent_viewers,
    follower_count,
    chat_messages_delta,
    stream_uptime_seconds
) VALUES
    -- Broadcast 1 snapshots (Alice playing League)
    (1, 1001, 2001, '2025-10-20 14:00:00+00', 120, 5000, 0, 0),
    (1, 1001, 2001, '2025-10-20 14:30:00+00', 145, 5005, 950, 1800),
    (1, 1001, 2001, '2025-10-20 15:00:00+00', 160, 5012, 1100, 3600),
    (1, 1001, 2001, '2025-10-20 15:30:00+00', 155, 5019, 1050, 5400),
    (1, 1001, 2001, '2025-10-20 16:00:00+00', 165, 5027, 1200, 7200),
    (1, 1001, 2001, '2025-10-20 16:30:00+00', 170, 5035, 1250, 9000),
    (1, 1001, 2001, '2025-10-20 17:00:00+00', 220, 5040, 1800, 10800),
    (1, 1001, 2001, '2025-10-20 17:30:00+00', 200, 5045, 1500, 12600),
    (1, 1001, 2001, '2025-10-20 18:00:00+00', 180, 5045, 1150, 14400),

    -- Broadcast 6 snapshots (Carol in trending game vs non-trending)
    (6, 1003, 2005, '2025-10-25 10:00:00+00', 650, 8000, 0, 0),
    (6, 1003, 2005, '2025-10-25 11:00:00+00', 900, 8100, 1500, 3600),
    (6, 1003, 2005, '2025-10-25 12:00:00+00', 1200, 8200, 2000, 7200),

    (7, 1003, 2001, '2025-10-26 11:00:00+00', 50, 8520, 0, 0),
    (7, 1003, 2001, '2025-10-26 12:00:00+00', 40, 8522, 400, 3600),
    (7, 1003, 2001, '2025-10-26 13:00:00+00', 45, 8525, 400, 7200);

\echo '✓ Inserted 15 sample broadcast snapshots'

-- ============================================================================
-- Sample Streamer Statistics
-- ============================================================================

INSERT INTO streamer_statistics (
    streamer_id,
    calculation_date,
    total_broadcasts,
    total_streaming_hours,
    unique_categories_streamed,
    average_concurrent_viewers,
    average_chat_rate,
    engagement_consistency,
    follower_gain_30d,
    follower_velocity,
    category_switching_frequency
) VALUES
    (1001, '2025-10-29', 12, 48.5, 4, 165.50, 1.85, 0.15, 245, 5.05, 2.5),
    (1002, '2025-10-29', 15, 60.0, 2, 205.00, 2.15, 0.08, 310, 5.17, 0.8),
    (1003, '2025-10-29', 8, 32.0, 2, 450.00, 0.45, 1.25, 325, 10.16, 1.0),
    (1004, '2025-10-29', 28, 112.0, 1, 95.00, 1.95, 0.12, 150, 1.34, 0.0),
    (1005, '2025-10-29', 10, 40.0, 5, 85.00, 1.65, 0.18, 120, 3.00, 3.2);

\echo '✓ Inserted 5 sample streamer statistics'

COMMIT;

\echo ''
\echo '============================================================================'
\echo 'Sample Data Insertion Complete!'
\echo '============================================================================'
\echo ''
\echo 'Summary:'
\echo '  • 5 streamers with diverse profiles'
\echo '  • 6 categories (2 trending, 4 evergreen)'
\echo '  • 8 broadcasts across different streamers and categories'
\echo '  • 15 time-series snapshots demonstrating engagement patterns'
\echo '  • 5 pre-computed statistics records'
\echo ''
\echo 'Key Test Scenarios:'
\echo '  1. Alice (1001): High engagement across multiple categories = HIDDEN GEM'
\echo '  2. Bob (1002): Personality-driven Just Chatting = HIDDEN GEM'
\echo '  3. Carol (1003): Game-hype dependent (high viewers in trending, low otherwise)'
\echo '  4. Dave (1004): Consistent but slower growth'
\echo '  5. Eve (1005): High versatility indicator'
\echo ''
\echo '============================================================================'
