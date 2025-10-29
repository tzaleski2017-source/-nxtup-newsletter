# Twitch Analytics Platform - Database Schema

A PostgreSQL database schema designed for identifying high-potential "hidden gem" Twitch streamers through predictive analytics.

## Overview

This database schema enables the collection and analysis of Twitch streaming data to distinguish **personality-driven growth** from **game-hype growth**. The goal is to identify streamers who maintain strong audience engagement across multiple content categories—key indicators of long-term talent potential for agents.

## Architecture

### Core Design Principles

1. **Time-Series First**: High-frequency snapshot data (every 15 minutes) enables detailed engagement tracking
2. **Category Attribution**: Every metric is linkable to the specific game/category being streamed
3. **Engagement Over Viewership**: Chat activity per viewer is prioritized over raw viewer counts
4. **Normalized Structure**: Clean separation of entities with appropriate foreign key constraints

### Database Tables

#### 1. `streamers` (Master Entity)
Stores static information about tracked Twitch streamers.

**Key Fields:**
- `streamer_id` (PK): Twitch's immutable user ID
- `username`: Current Twitch username
- `discovered_at`: When we started tracking
- `is_active`: Soft-delete flag

#### 2. `categories` (Reference Data)
Game and content category taxonomy.

**Key Fields:**
- `category_id` (PK): Twitch category/game ID
- `category_name`: Display name (e.g., "League of Legends")
- `is_trending`: Flag for trending games (critical for hype detection)

#### 3. `broadcasts` (Session Aggregates)
Individual streaming sessions.

**Key Fields:**
- `broadcast_id` (PK): Auto-incrementing internal ID
- `streamer_id` (FK): Links to streamers table
- `primary_category_id` (FK): Main category for this stream
- `started_at`, `ended_at`: Temporal boundaries
- `average_viewers`, `peak_viewers`: Computed from snapshots
- `follower_gain`: Net new followers during stream

#### 4. `broadcast_snapshots` ⭐ (Core Analytics Table)
Time-series data captured every 15 minutes during broadcasts.

**Key Fields:**
- `snapshot_id` (PK): Auto-incrementing ID
- `broadcast_id` (FK): Links to broadcast
- `streamer_id` (FK): Denormalized for performance
- `category_id` (FK): Category at this moment (may differ from broadcast's primary)
- `snapshot_timestamp`: Exact capture time
- `concurrent_viewers`: Viewers at this moment
- `follower_count`: Cumulative followers at this moment
- `chat_messages_delta`: New messages since last snapshot

**Why This Matters:**
The `chat_messages_delta / concurrent_viewers` ratio is the primary metric for engagement. High values indicate strong personality-driven communities.

#### 5. `streamer_statistics` (Pre-computed Aggregates)
Daily batch-computed metrics for dashboard performance.

**Key Fields:**
- `streamer_id` (PK, composite with calculation_date)
- `calculation_date`: Date these stats were calculated
- `average_chat_rate`: Messages per viewer per hour
- `engagement_consistency`: Standard deviation (lower = more consistent)
- `follower_velocity`: Followers per streaming hour
- `unique_categories_streamed`: Content diversity indicator

## Setup Instructions

### Prerequisites

1. **Neon PostgreSQL Account**
   - Create a free account at [console.neon.tech](https://console.neon.tech)
   - Create a new project for this database

2. **Claude Code with Neon MCP**
   - The Neon MCP configuration has been added to `.mcp.json`
   - Restart Claude Code to load the MCP server
   - Authenticate via OAuth when prompted

3. **PostgreSQL Client** (Alternative)
   - `psql` command-line tool, OR
   - GUI client like pgAdmin, DBeaver, or TablePlus

### Option 1: Using Neon MCP (Recommended)

Once Claude Code is restarted and Neon MCP is authenticated:

```
Ask Claude: "Please execute the schema/setup.sql file against my Neon database"
```

Claude Code will use the Neon MCP to execute all schema files in the correct order.

### Option 2: Using psql Command Line

1. Get your Neon connection string from the Neon console
2. Execute the setup script:

```bash
cd schema
psql "postgresql://[USER]:[PASSWORD]@[HOST]/[DATABASE]?sslmode=require" -f setup.sql
```

### Option 3: Using a GUI Client

1. Connect to your Neon database using your preferred GUI client
2. Execute the files in order:
   - `schema/01_streamers.sql`
   - `schema/02_categories.sql`
   - `schema/03_broadcasts.sql`
   - `schema/04_broadcast_snapshots.sql`
   - `schema/05_streamer_statistics.sql`

## Verification

After setup, verify the schema:

```sql
-- List all tables
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Should return:
-- - broadcasts
-- - broadcast_snapshots
-- - categories
-- - streamer_statistics
-- - streamers
```

## Loading Sample Data

To test the schema with representative data:

```bash
psql "your_connection_string" -f docs/sample_data.sql
```

This inserts:
- 5 streamers with diverse profiles
- 6 categories (2 trending, 4 evergreen)
- 8 broadcasts across different scenarios
- 15 time-series snapshots
- 5 pre-computed statistics records

**Test Personas:**
1. **Alice** (hidden_gem_alice): High engagement across multiple categories ✅ HIDDEN GEM
2. **Bob** (rising_bob): Personality-driven "Just Chatting" streamer ✅ HIDDEN GEM
3. **Carol** (hype_hunter_carol): Game-hype dependent (high in trending games only) ❌
4. **Dave** (consistent_dave): Consistent but slower growth
5. **Eve** (versatile_eve): High category diversity indicator ✅

## Example Analytical Queries

See `docs/example_queries.sql` for 7 comprehensive example queries:

1. **High-Engagement Streamers**: Find streamers with chat engagement above threshold
2. **Category-Independent Performance**: THE KEY QUERY for personality vs. game-hype
3. **Game-Hype Detection**: Identify streamers dependent on trending games
4. **Follower Velocity**: Growth rate normalized by streaming hours
5. **Hidden Gem Composite Score**: Multi-signal ranking algorithm
6. **Time-Series Retention**: Viewer retention curves during streams
7. **Category Switching Impact**: Performance changes when switching games

### Quick Example: Find Hidden Gems

```sql
SELECT
    s.username,
    COUNT(DISTINCT b.primary_category_id) as categories_count,
    ROUND(AVG(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)), 3) as avg_engagement,
    ROUND(AVG(bs.concurrent_viewers)::NUMERIC, 0) as avg_viewers
FROM streamers s
JOIN broadcasts b ON s.streamer_id = b.streamer_id
JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
WHERE b.started_at > NOW() - INTERVAL '60 days'
GROUP BY s.streamer_id, s.username
HAVING COUNT(DISTINCT b.primary_category_id) >= 3  -- Multi-category
   AND AVG(bs.chat_messages_delta::NUMERIC / NULLIF(bs.concurrent_viewers, 0)) > 5.0  -- High engagement
ORDER BY avg_engagement DESC
LIMIT 10;
```

## Key Metrics Explained

### Engagement Rate
```
chat_messages_delta / concurrent_viewers / time_interval
```
Measures how actively the audience participates. High values (>5.0 per hour) indicate strong community engagement.

### Follower Velocity
```
total_followers_gained / hours_streamed
```
Normalizes growth by effort. More efficient than absolute follower counts.

### Category-Independent Score
```
STDDEV(engagement_rate_across_categories)
```
Low standard deviation means consistent engagement regardless of game = personality-driven.

### Hidden Gem Composite Score
Combines:
- Engagement rate (weight: 20)
- Follower velocity (weight: 10)
- Category diversity (weight: 15)
- Consistency bonus (20 points if engagement_std_dev < 1)
- Undiscovered bonus (30 points if avg_viewers < 200)
- Popularity penalty (-50 points if avg_viewers > 1000)

## Project Components

This platform consists of three main components:

### 1. Database Schema (`schema/`)
PostgreSQL tables optimized for time-series analytics of streaming data.

### 2. Discovery Utility (`discover.py`)
Command-line tool for finding and adding new streamers to track.

**Purpose**: Populates the `streamers` table with interesting "hidden gem" candidates.

**Usage**:
```bash
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10
```

**Features**:
- Search by game category and viewer count
- Automatic duplicate detection
- Dry-run mode for testing
- Detailed progress logging

**See**: [DISCOVERY.md](DISCOVERY.md) for complete documentation

### 3. Data Ingestion Service (`ingestion/`)
Real-time data collection service that tracks active streamers.

**Purpose**: Continuously collects viewership, follower, and chat engagement data.

**Architecture**:
- EventSub WebSocket: Stream start/end events
- IRC Chat: Real-time message counting
- Scheduled Poller: 15-minute metric snapshots

**See**: [ingestion/README.md](ingestion/README.md) for complete documentation

## Complete Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Setup Database Schema                                        │
│    → Execute schema/setup.sql                                   │
│    → Tables created in PostgreSQL (Neon)                        │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Discover Streamers (discover.py)                             │
│    → Search Twitch for streamers matching criteria             │
│    → Add to streamers table (is_active = true)                 │
│    Example: 50-250 viewer "hidden gems"                        │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Start Ingestion Service (ingestion/main.py)                  │
│    → Loads active streamers from database                      │
│    → Subscribes to stream events                               │
│    → Joins IRC channels                                        │
│    → Begins 15-minute snapshot collection                      │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Data Collection (Automatic)                                  │
│    → Broadcasts created when streams go live                   │
│    → Snapshots collected every 15 minutes                      │
│    → Chat messages counted in real-time                        │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Analysis & Modeling (Future)                                 │
│    → Query historical data from database                       │
│    → Calculate engagement metrics                              │
│    → Train predictive models                                   │
│    → Identify "hidden gems" for newsletter                     │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Step 1: Database Setup
```bash
cd schema
psql $DATABASE_URL -f setup.sql
```

### Step 2: Discover Streamers
```bash
# Find small "Just Chatting" streamers
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10

# Verify additions
psql $DATABASE_URL -c "SELECT COUNT(*) FROM streamers WHERE is_active = true;"
```

### Step 3: Start Data Collection
```bash
cd ingestion
python -m ingestion.main
```

### Step 4: Monitor & Analyze
```bash
# Check collected data
psql $DATABASE_URL -c "SELECT COUNT(*) FROM broadcast_snapshots;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM broadcasts WHERE ended_at IS NULL;"
```

## Schema Modifications

### Adding Indexes
If you find specific query patterns are slow, add indexes:

```sql
CREATE INDEX idx_custom_name ON table_name(column_name);
```

### Partitioning broadcast_snapshots
For production scale (millions of snapshots):

```sql
-- Partition by month
CREATE TABLE broadcast_snapshots_2025_11 PARTITION OF broadcast_snapshots
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
```

### Adding Computed Columns
Example: Add engagement_rate directly to snapshots:

```sql
ALTER TABLE broadcast_snapshots
ADD COLUMN engagement_rate NUMERIC(10,4)
GENERATED ALWAYS AS (
    chat_messages_delta::NUMERIC / NULLIF(concurrent_viewers, 0)
) STORED;
```

## Database Maintenance

### Regular Tasks

1. **Vacuum/Analyze** (weekly): Keep statistics current
```sql
VACUUM ANALYZE;
```

2. **Reindex** (monthly): Optimize index performance
```sql
REINDEX DATABASE your_database_name;
```

3. **Archive Old Data** (quarterly): Move snapshots >1 year to archive table
```sql
INSERT INTO broadcast_snapshots_archive
SELECT * FROM broadcast_snapshots
WHERE snapshot_timestamp < NOW() - INTERVAL '1 year';

DELETE FROM broadcast_snapshots
WHERE snapshot_timestamp < NOW() - INTERVAL '1 year';
```

## Security Considerations

- **Never commit database credentials** to version control
- Use environment variables for connection strings
- Implement row-level security (RLS) if multi-tenant
- Regularly rotate API keys and database passwords
- Enable Neon's IP allowlist for production databases

## Performance Optimization

### Expected Data Volume
- **Daily snapshots**: ~32,000/day (1000 streamers × 4/hour × 8 hours)
- **Monthly snapshots**: ~960,000/month
- **Yearly snapshots**: ~11.5M/year

### Monitoring Queries

```sql
-- Table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Slow queries (requires pg_stat_statements extension)
SELECT query, calls, mean_exec_time, max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Contributing

This is the foundational schema for the Twitch analytics platform. Future enhancements:

- [ ] Add newsletter subscription management tables
- [ ] Add ML model prediction storage
- [ ] Add audit logging tables
- [ ] Implement materialized views for common aggregations
- [ ] Add full-text search on stream titles/descriptions
- [ ] Add webhook event tracking for real-time updates

## License

[Your License Here]

## Support

For questions or issues with the database schema, please open an issue in this repository.

---

**Built for identifying the next generation of streaming talent** 🚀
