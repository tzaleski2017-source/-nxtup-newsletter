# Twitch Data Ingestion Service

A hybrid polling and event-driven service for collecting Twitch streamer analytics data in real-time.

## Overview

This service continuously monitors tracked Twitch streamers and collects:
- **Stream events**: When streams start and end (via EventSub WebSocket)
- **Chat messages**: Real-time message counting (via IRC)
- **Viewership metrics**: Concurrent viewers every 15 minutes (via Helix API)
- **Follower metrics**: Total followers every 15 minutes (via Helix API)

All data is stored in a PostgreSQL database (Neon) following the schema defined in `../schema/`.

## Architecture

### Hybrid Design: Events + Polling

```
┌─────────────────────────────────────────────────────────────────┐
│                    Twitch Data Ingestion Service                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │   EventSub WS    │  │   IRC Chat       │  │   Poller     │ │
│  │   (Stream        │  │   (Message       │  │   (15-min    │ │
│  │    Events)       │  │    Counting)     │  │    Metrics)  │ │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘ │
│           │                     │                    │         │
│           v                     v                    v         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │             Chat Counter Manager (In-Memory)             │  │
│  │           {broadcast_id: message_count}                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                 │
│                              v                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │               Database (PostgreSQL/Neon)                 │  │
│  │  - broadcasts (stream sessions)                          │  │
│  │  - broadcast_snapshots (15-min time-series data)         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Components

1. **EventSub Handler** (`twitch_eventsub.py`)
   - Subscribes to `stream.online` and `stream.offline` events
   - Creates broadcast records when streams start
   - Updates broadcast records when streams end
   - Uses WebSocket transport (no public endpoint needed)

2. **Chat Listener** (`twitch_chat.py`)
   - Connects to Twitch IRC
   - Joins channels for tracked streamers
   - Increments in-memory counter for each message
   - Lightweight and efficient

3. **Snapshot Poller** (`poller.py`)
   - Runs every 15 minutes (0, 15, 30, 45 past the hour)
   - For each active broadcast:
     - Fetches current viewer count from Twitch API
     - Fetches current follower count from Twitch API
     - Reads and **resets** chat message counter
     - Writes snapshot to database

4. **Chat Counter Manager** (`state.py`)
   - In-memory storage: `{broadcast_id: message_count}`
   - Thread-safe operations using `asyncio.Lock`
   - Reset after each snapshot (critical for accurate delta)

5. **Database Layer** (`database.py`)
   - Async PostgreSQL operations using `asyncpg`
   - Connection pooling for performance
   - All SQL queries aligned with existing schema

## Data Flow

### Flow 1: Stream Starts
```
Twitch EventSub → stream.online event
  ↓
Create record in broadcasts table
  ↓
Initialize chat counter to 0
```

### Flow 2: Chat Messages
```
Twitch IRC → message received
  ↓
Lookup active broadcast for channel
  ↓
Increment chat counter (in-memory)
```

### Flow 3: 15-Minute Snapshot
```
Scheduler triggers (every 15 min)
  ↓
For each active broadcast:
  - Get current viewers (Twitch API)
  - Get current followers (Twitch API)
  - Read and reset chat counter
  - Calculate uptime
  ↓
Insert into broadcast_snapshots table
```

### Flow 4: Stream Ends
```
Twitch EventSub → stream.offline event
  ↓
Update broadcasts.ended_at
  ↓
Calculate broadcasts.duration_seconds
  ↓
Remove chat counter (cleanup)
```

## Installation

### Prerequisites

- Python 3.10 or higher
- PostgreSQL database (Neon recommended)
- Twitch API credentials
- Active Twitch account

### Step 1: Clone Repository

```bash
cd -nxtup-newsletter/ingestion
```

### Step 2: Install Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your actual values
nano .env  # or vim, code, etc.
```

### Step 4: Get Twitch API Credentials

#### Client ID and Secret

1. Go to https://dev.twitch.tv/console/apps
2. Log in with your Twitch account
3. Click "Register Your Application"
4. Fill in:
   - **Name**: Twitch Analytics Ingestion
   - **OAuth Redirect URLs**: http://localhost:3000 (not used, but required)
   - **Category**: Analytics Tool
5. Click "Create"
6. Copy the **Client ID**
7. Click "New Secret" and copy the **Client Secret**
8. Add both to `.env`:
   ```
   TWITCH_CLIENT_ID=your_client_id_here
   TWITCH_CLIENT_SECRET=your_client_secret_here
   ```

#### User Access Token

**Option 1: Twitch CLI (Recommended)**

```bash
# Install Twitch CLI: https://github.com/twitchdev/twitch-cli
# Then generate token:
twitch token -u -s "user:read:email"

# Copy the access token to .env
```

**Option 2: Token Generator Website**

1. Go to https://twitchtokengenerator.com/
2. Select "Custom Scope Token"
3. Check: `user:read:email`
4. Click "Generate Token"
5. Authorize with Twitch
6. Copy the **Access Token** to `.env`:
   ```
   TWITCH_ACCESS_TOKEN=your_token_here
   ```

### Step 5: Configure Database

Get your Neon connection string:

1. Go to https://console.neon.tech/
2. Select your project
3. Go to "Connection Details"
4. Copy the connection string
5. Add to `.env`:
   ```
   DATABASE_URL=postgresql://user:password@host.neon.tech/dbname?sslmode=require
   ```

### Step 6: Add Tracked Streamers

Edit `.env` and add comma-separated usernames:

```
TRACKED_STREAMERS=streamer1,streamer2,streamer3
```

**Note**: Streamers will be auto-created in the database on first run if they don't exist.

## Usage

### Running the Service

```bash
# From the project root
python -m ingestion.main

# Or from within ingestion directory
cd ingestion
python main.py
```

### Expected Output

```
================================================================================
Twitch Data Ingestion Service - Starting
================================================================================

[Init] Connecting to database...
[Database] Connection pool created
[Init] ✓ Database connected and healthy
[Init] ✓ Chat counter manager initialized

[Init] Authenticating with Twitch API...
[Init] ✓ Twitch API authenticated

[Init] Loading tracked streamers...
[Init] ✓ Tracking 3 streamers:
[Init]   - streamer1 (ID: 123456789)
[Init]   - streamer2 (ID: 987654321)
[Init]   - streamer3 (ID: 456789123)

[Start] Launching service components...
[Start] Starting EventSub handler...
[EventSub] WebSocket connection started
[EventSub] Subscribed to events for streamer1 (123456789)
[EventSub] Subscribed to events for streamer2 (987654321)
[EventSub] Subscribed to events for streamer3 (456789123)
[EventSub] ✓ Listening for events from 3 streamers
[Start] ✓ EventSub handler running
[Start] Starting chat listener...
[ChatListener] Initialized for 3 channels: streamer1, streamer2, streamer3
[ChatListener] Connected as your_bot_name
[ChatListener] Joined channels: streamer1, streamer2, streamer3
[Start] ✓ Chat listener running
[Start] Starting snapshot poller...
[Poller] Initialized with 15-minute interval
[Poller] ✓ Started (runs every 15 minutes)
[Start] ✓ Snapshot poller running

================================================================================
🚀 Twitch Data Ingestion Service is RUNNING
================================================================================

Monitoring:
  • 3 streamers
  • Stream events: stream.online, stream.offline
  • Chat messages: real-time counting
  • Snapshots: every 15 minutes

Press Ctrl+C to stop
================================================================================
```

### When a Stream Starts

```
[EventSub] 🔴 Stream ONLINE: streamer1 (ID: 123456789)
[Database] Created broadcast 42 for streamer 123456789
[ChatCounter] Initialized counter for broadcast 42
[EventSub] ✓ Created broadcast 42 for streamer1
```

### During Stream (Every 15 Minutes)

```
[Poller] === Starting snapshot collection at 2025-10-29T15:30:00Z ===
[Poller] Found 1 active broadcast(s)
[Poller] ✓ Snapshot 42: 1523 viewers, 847 messages, 45682 followers
[Poller] === Snapshot collection complete: 1 success, 0 failed ===
```

### When a Stream Ends

```
[EventSub] ⚫ Stream OFFLINE: streamer1 (ID: 123456789)
[Database] Ended broadcast 42
[ChatCounter] Removed counter for broadcast 42 (final count: 123)
[EventSub] ✓ Ended broadcast 42 for streamer1
```

### Stopping the Service

Press `Ctrl+C`:

```
[Signal] Received signal 2

[Shutdown] Stopping service...
[Shutdown] ✓ Poller stopped
[Shutdown] ✓ EventSub stopped
[Shutdown] ✓ Chat listener stopped
[Shutdown] ✓ Database connection closed
[Shutdown] ✓ Shutdown complete
[Main] Service stopped
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TWITCH_CLIENT_ID` | Yes | - | Twitch application Client ID |
| `TWITCH_CLIENT_SECRET` | Yes | - | Twitch application Client Secret |
| `TWITCH_ACCESS_TOKEN` | Yes | - | User access token for EventSub/IRC |
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `TRACKED_STREAMERS` | Yes | - | Comma-separated usernames |
| `SNAPSHOT_INTERVAL_MINUTES` | No | 15 | Polling interval (5, 10, 15, 20, 30) |
| `LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Snapshot Interval

The default is 15 minutes, which aligns with the database schema design. You can change this, but:

- Must be a divisor of 60 for clean scheduling (e.g., 5, 10, 15, 20, 30)
- Shorter intervals = more API calls (watch rate limits)
- Longer intervals = less granular data

**Recommendation**: Keep at 15 minutes unless you have specific needs.

## Database Schema

This service writes to the following tables:

### `broadcasts`
Created when stream starts, updated when stream ends.

```sql
broadcast_id         BIGSERIAL PRIMARY KEY
streamer_id          BIGINT (FK to streamers)
primary_category_id  BIGINT (FK to categories)
stream_title         TEXT
started_at           TIMESTAMPTZ
ended_at             TIMESTAMPTZ  -- NULL while live
duration_seconds     INTEGER      -- Computed on end
```

### `broadcast_snapshots`
Created every 15 minutes for active broadcasts.

```sql
snapshot_id          BIGSERIAL PRIMARY KEY
broadcast_id         BIGINT (FK to broadcasts)
streamer_id          BIGINT (FK to streamers, denormalized)
category_id          BIGINT (FK to categories)
snapshot_timestamp   TIMESTAMPTZ
concurrent_viewers   INTEGER      -- From Twitch API
follower_count       BIGINT       -- From Twitch API
chat_messages_delta  INTEGER      -- From chat counter (reset each snapshot)
stream_uptime_seconds INTEGER     -- Calculated from started_at
```

## Monitoring

### Health Checks

The service doesn't expose an HTTP endpoint by default. To monitor health:

1. **Check process is running**:
   ```bash
   ps aux | grep "python.*ingestion.main"
   ```

2. **Check database connectivity**:
   ```bash
   # The service logs health check results on startup
   # Look for: "[Init] ✓ Database connected and healthy"
   ```

3. **Check recent snapshots**:
   ```sql
   SELECT COUNT(*), MAX(snapshot_timestamp)
   FROM broadcast_snapshots
   WHERE snapshot_timestamp > NOW() - INTERVAL '1 hour';
   ```

### Logs

The service logs to stdout. For production, redirect to a file or use a log aggregator:

```bash
# Log to file
python -m ingestion.main >> ingestion.log 2>&1

# Log to file with rotation (using logrotate)
python -m ingestion.main | tee -a ingestion.log
```

### Metrics to Monitor

1. **Snapshot success rate**: Should be 100% for active broadcasts
2. **EventSub connection**: Should reconnect automatically if dropped
3. **Chat message counts**: Should increase during active streams
4. **Database connection pool**: Monitor for connection leaks

## Troubleshooting

### Issue: "Database health check failed"

**Causes**:
- Database not reachable
- Incorrect connection string
- Database not initialized (schema not created)

**Solution**:
```bash
# Test connection manually
psql "your_connection_string" -c "SELECT 1;"

# Ensure schema is created
cd ../schema
psql "your_connection_string" -f setup.sql
```

### Issue: "No tracked streamers in database"

**Causes**:
- `TRACKED_STREAMERS` not set in `.env`
- Streamers not yet created in database

**Solution**:
The service automatically creates streamers on first run. Verify:
```sql
SELECT * FROM streamers WHERE is_active = true;
```

### Issue: "EventSub subscription failed"

**Causes**:
- Invalid access token
- Token doesn't have required scopes
- Streamer ID not found

**Solution**:
```bash
# Regenerate access token with correct scopes
twitch token -u -s "user:read:email"

# Verify token is valid
curl -H "Authorization: Bearer your_token" \
     https://id.twitch.tv/oauth2/validate
```

### Issue: "Chat listener not receiving messages"

**Causes**:
- Streamer not live
- Chat is in followers-only or slow mode
- Access token invalid

**Solution**:
- Verify streamer is actually live
- Check chat restrictions in streamer's chat settings
- Test IRC connection manually:
  ```bash
  # Using a Twitch IRC client
  telnet irc.chat.twitch.tv 6667
  ```

### Issue: "Snapshots not being created"

**Causes**:
- Poller not started
- Broadcast ended but not marked in database
- API rate limits exceeded

**Solution**:
```bash
# Check active broadcasts
SELECT * FROM broadcasts WHERE ended_at IS NULL;

# Check recent snapshots
SELECT * FROM broadcast_snapshots ORDER BY snapshot_timestamp DESC LIMIT 10;

# Check Twitch API rate limits (in service logs)
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio pytest-mock

# Run tests
pytest tests/
```

### Code Structure

```
ingestion/
├── __init__.py           # Package initialization
├── config.py             # Configuration (Pydantic settings)
├── state.py              # Chat counter manager (in-memory state)
├── database.py           # Database operations (asyncpg)
├── twitch_chat.py        # IRC chat listener (TwitchIO)
├── twitch_eventsub.py    # EventSub handler (pyTwitchAPI)
├── poller.py             # Snapshot collector (APScheduler)
├── main.py               # Application entry point
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
└── README.md             # This file
```

### Adding New Streamers

**Option 1: Update .env and restart**

```bash
# Edit .env
TRACKED_STREAMERS=streamer1,streamer2,new_streamer

# Restart service
```

**Option 2: Add directly to database**

```sql
-- Get Twitch user ID first (use Twitch API or website)
INSERT INTO streamers (streamer_id, username, is_active)
VALUES (123456789, 'new_streamer', true);

-- Restart service to pick up new streamer
```

### Scaling Considerations

**Current Architecture (MVP)**:
- Single process
- In-memory state
- Suitable for: 10-50 streamers

**For Horizontal Scaling**:
1. **Replace in-memory state with Redis**:
   - Chat counters: `INCR chat_counter:{broadcast_id}`
   - Atomic operations: `GETDEL` for read-and-reset

2. **Separate components into microservices**:
   - EventSub service (stateless)
   - Chat listener service (stateless)
   - Poller service (stateless)
   - Redis for shared state

3. **Add message queue**:
   - RabbitMQ or Kafka for event processing
   - Decouple event capture from database writes

## API Rate Limits

### Twitch Helix API

- **Rate Limit**: 800 requests per minute per client ID
- **Our Usage**:
  - Snapshot collection: 2 API calls per streamer per 15 minutes
  - 10 streamers = 20 calls per 15 minutes = 80 calls per hour
  - Well within limits (< 1% utilization)

### Scaling Calculation

Maximum streamers with 15-minute interval:
```
800 requests/min × 60 min/hour = 48,000 requests/hour
2 API calls/streamer/snapshot × 4 snapshots/hour = 8 calls/streamer/hour
48,000 / 8 = 6,000 streamers (theoretical max)

Practical limit (50% buffer): ~3,000 streamers
```

## Future Enhancements

### Planned Features

1. **Backfill Support**
   - Handle missed snapshots during downtime
   - Query Twitch API for historical data (limited)

2. **Dynamic Streamer Discovery**
   - Auto-add streamers based on criteria
   - Monitor trending/rising streamers

3. **Enhanced Monitoring**
   - Prometheus metrics endpoint
   - Grafana dashboard
   - Alert on collection failures

4. **Category Enrichment**
   - Auto-populate categories table
   - Track game metadata (IGDB integration)

5. **Aggregate Computation**
   - Compute broadcast aggregates (avg_viewers, peak_viewers)
   - Populate streamer_statistics table
   - Daily batch jobs for analytics

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review service logs for error messages
3. Open an issue in the project repository

## License

[Your License Here]

---

**Built for identifying the next generation of streaming talent** 🚀
