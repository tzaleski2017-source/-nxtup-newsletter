# Twitch Streamer Discovery Utility

A command-line tool for discovering and adding new Twitch streamers to the tracking database.

## Overview

The `discover.py` script searches Twitch for live streams matching specific criteria (game category and viewer count range) and adds new streamers to your database for tracking by the ingestion service.

## Purpose

The ingestion service (`ingestion/main.py`) only tracks streamers that exist in the `streamers` table with `is_active = true`. This discovery utility solves the cold-start problem by populating that table with interesting streamers to track.

## How It Works

```
1. Search Twitch API for live streams in specified game/category
   ↓
2. Filter streams by concurrent viewer count (min-max range)
   ↓
3. For each matching stream:
   ├─ Check if streamer already exists in database
   ├─ If new: Fetch full user profile from Twitch
   └─ Insert into streamers table (is_active = true)
   ↓
4. Continue until limit reached or no more streams
```

## Installation

The script uses the same dependencies as the ingestion service:

```bash
# Dependencies already installed if you set up ingestion service
pip install twitchAPI asyncpg python-dotenv
```

## Configuration

The script reads credentials from environment variables (`.env` file):

```bash
# Required in .env file
TWITCH_CLIENT_ID=your_client_id_here
TWITCH_CLIENT_SECRET=your_client_secret_here
DATABASE_URL=postgresql://user:pass@host.neon.tech/database?sslmode=require
```

These are the same credentials used by the ingestion service.

## Usage

### Basic Command

```bash
python discover.py --game-id <GAME_ID> --min-viewers <MIN> --max-viewers <MAX> --limit <LIMIT>
```

### Required Arguments

- `--game-id`: Twitch game/category ID to search
- `--min-viewers`: Minimum concurrent viewers
- `--max-viewers`: Maximum concurrent viewers

### Optional Arguments

- `--limit`: Maximum number of streamers to add (default: 10)
- `--dry-run`: Preview results without making database changes

### Examples

**Discover small "Just Chatting" streamers:**
```bash
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10
```

**Discover mid-size "League of Legends" streamers:**
```bash
python discover.py --game-id 21779 --min-viewers 100 --max-viewers 500 --limit 20
```

**Test without making changes (dry run):**
```bash
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 5 --dry-run
```

**Discover "Minecraft" streamers with specific criteria:**
```bash
python discover.py --game-id 27471 --min-viewers 75 --max-viewers 200 --limit 15
```

## Common Game IDs

| Game | Category ID |
|------|-------------|
| Just Chatting | 509658 |
| League of Legends | 21779 |
| Fortnite | 33214 |
| Minecraft | 27471 |
| Valorant | 516575 |
| Grand Theft Auto V | 32982 |
| Counter-Strike 2 | 32399 |
| Dota 2 | 29595 |
| Apex Legends | 511224 |
| Call of Duty: Warzone | 512710 |

**Finding Other Game IDs:**
1. Go to https://www.twitch.tv/directory
2. Click on a game
3. Check URL: `https://www.twitch.tv/directory/game/<GAME_NAME>?id=<GAME_ID>`
4. Use the `<GAME_ID>` parameter

Or use the Twitch API:
```bash
# Search for game by name
curl -H "Client-ID: YOUR_CLIENT_ID" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     "https://api.twitch.tv/helix/games?name=Minecraft"
```

## Output

### Success Example

```
============================================================
TWITCH STREAMER DISCOVERY
============================================================
Game ID: 509658
Viewer range: 50 - 250
Target limit: 5
Mode: LIVE
============================================================

Connecting to Twitch API...
✓ Authenticated

Connecting to database...
✓ Connected

Searching for streams in category 509658 with 50-250 viewers...
Target: 5 new streamer(s)

[1/5] Found: coolstreamer123 (127 viewers)
  → Fetching user profile...
  → Adding to database...
  ✓ Added coolstreamer123 (CoolStreamer123)

[2/5] Found: gamer456 (185 viewers)
  → Fetching user profile...
  ⊘ Already tracked, skipping

[3/5] Found: newstreamer789 (95 viewers)
  → Fetching user profile...
  → Adding to database...
  ✓ Added newstreamer789 (NewStreamer789)

... (continued)

============================================================
DISCOVERY SUMMARY:
============================================================
  Streams processed: 87
  Already tracked: 2
  Newly added: 5
============================================================
```

### Dry Run Example

```
DRY RUN MODE - No database changes will be made

Searching for streams in category 509658 with 50-250 viewers...
Target: 3 new streamer(s)

[1/3] Found: user123 (150 viewers)
  → Fetching user profile...
  ✓ Would add user123 (User123)

[2/3] Found: user456 (95 viewers)
  → Fetching user profile...
  ✓ Would add user456 (User456)

[3/3] Found: user789 (210 viewers)
  → Fetching user profile...
  ✓ Would add user789 (User789)

============================================================
DRY RUN SUMMARY:
============================================================

Would add the following streamers:
  1. user123 (User123) - 150 viewers
  2. user456 (User456) - 95 viewers
  3. user789 (User789) - 210 viewers
============================================================
```

## Verification

After running the discovery script, verify streamers were added:

```sql
-- Check recently added streamers
SELECT
    streamer_id,
    username,
    display_name,
    discovered_at,
    is_active
FROM streamers
WHERE is_active = true
ORDER BY discovered_at DESC
LIMIT 10;
```

Or using psql:
```bash
psql $DATABASE_URL -c "SELECT streamer_id, username, discovered_at FROM streamers ORDER BY discovered_at DESC LIMIT 5;"
```

## Integration with Ingestion Service

Once streamers are added to the database, the ingestion service will automatically track them:

```bash
# 1. Discover streamers
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10

# 2. Verify streamers added
psql $DATABASE_URL -c "SELECT COUNT(*) FROM streamers WHERE is_active = true;"

# 3. Start ingestion service
cd ingestion
python -m ingestion.main
```

The ingestion service will:
- Load all active streamers on startup
- Subscribe to their stream events (online/offline)
- Join their IRC channels for chat tracking
- Collect snapshots every 15 minutes when they're live

## Workflow

```
┌────────────────────────────────────────────────────────┐
│  1. Run discover.py                                    │
│     → Finds streamers matching criteria                │
│     → Adds to streamers table (is_active = true)       │
└────────────────────┬───────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────┐
│  2. Start/Restart ingestion service                    │
│     → Loads active streamers                           │
│     → Subscribes to events                             │
│     → Begins tracking                                  │
└────────────────────┬───────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────┐
│  3. Data collection begins                             │
│     → Broadcasts created when streams go live          │
│     → Snapshots collected every 15 minutes             │
│     → Chat messages counted in real-time               │
└────────────────────┬───────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────┐
│  4. Analysis ready                                     │
│     → Historical data accumulated                      │
│     → Ready for predictive modeling                    │
└────────────────────────────────────────────────────────┘
```

## Strategy: Finding "Hidden Gems"

### Viewer Count Sweet Spot

**50-250 viewers** is ideal for "hidden gem" discovery because:
- **Below 50**: Often brand new or inconsistent streamers
- **50-250**: Established enough to have a community, not yet "discovered"
- **Above 250**: Already on the radar, less "hidden"

### Recommended Approach

**Phase 1: Broad Discovery**
```bash
# Cast a wide net across popular categories
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 20  # Just Chatting
python discover.py --game-id 21779 --min-viewers 50 --max-viewers 250 --limit 20   # League of Legends
python discover.py --game-id 27471 --min-viewers 50 --max-viewers 250 --limit 20   # Minecraft
```

**Phase 2: Targeted Discovery**
```bash
# Focus on specific niches or viewer ranges
python discover.py --game-id 509658 --min-viewers 100 --max-viewers 200 --limit 15
python discover.py --game-id 516575 --min-viewers 75 --max-viewers 150 --limit 10
```

**Phase 3: Ongoing Discovery**
```bash
# Schedule regular discovery runs (e.g., weekly cron job)
# Different categories on different days
```

### Multi-Category Coverage

Discover streamers across diverse categories to identify versatile personalities:

```bash
# Monday: Social categories
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10  # Just Chatting

# Tuesday: Competitive games
python discover.py --game-id 21779 --min-viewers 50 --max-viewers 250 --limit 10   # League of Legends
python discover.py --game-id 516575 --min-viewers 50 --max-viewers 250 --limit 10  # Valorant

# Wednesday: Sandbox/Creative
python discover.py --game-id 27471 --min-viewers 50 --max-viewers 250 --limit 10   # Minecraft

# And so on...
```

## Data Added to Database

For each discovered streamer, the script inserts:

```sql
INSERT INTO streamers (
    streamer_id,          -- Twitch user ID (from API)
    username,             -- Lowercase username (from API)
    display_name,         -- Capitalized display name (from API)
    profile_image_url,    -- Avatar URL (from API)
    description,          -- Channel description (from API)
    account_created_at,   -- When Twitch account created (from API)
    is_active             -- Set to TRUE (enables tracking)
    -- discovered_at      -- Auto-set to NOW()
    -- created_at         -- Auto-set to NOW()
    -- updated_at         -- Auto-set to NOW()
)
```

## Troubleshooting

### No Streamers Found

**Problem**: Script processes many streams but finds no matches.

**Causes**:
1. Viewer range too narrow or high
2. Wrong game ID
3. No live streams in that category

**Solutions**:
```bash
# Try wider viewer range
python discover.py --game-id 509658 --min-viewers 10 --max-viewers 500 --limit 5

# Try different game (Just Chatting always has streams)
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 5

# Use dry-run to see what would match
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 5 --dry-run
```

### All Streamers Already Tracked

**Problem**: Script skips all found streamers (already tracked).

**Solution**: This is expected if you've run the same query before. Try:
- Different game ID
- Different viewer range
- Higher limit to go deeper in results
- Wait and run again later (different streamers will be live)

### Database Connection Error

**Problem**: `Error connecting to database`

**Causes**:
1. DATABASE_URL not set or incorrect
2. Database not reachable
3. Network issues

**Solutions**:
```bash
# Test database connection
psql $DATABASE_URL -c "SELECT 1;"

# Verify .env file has DATABASE_URL
cat .env | grep DATABASE_URL

# Test with dry-run (doesn't need database)
python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 3 --dry-run
```

### Twitch API Authentication Error

**Problem**: `Error connecting to Twitch API`

**Causes**:
1. TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET not set
2. Invalid credentials
3. Network issues

**Solutions**:
```bash
# Verify credentials in .env
cat .env | grep TWITCH

# Test credentials manually
curl -X POST "https://id.twitch.tv/oauth2/token" \
  -d "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials"
```

### Script Hangs or Times Out

**Problem**: Script appears stuck or takes very long.

**Causes**:
1. Very high viewer range (processing many streams)
2. Network latency
3. Database slow query

**Solutions**:
- Use lower `--limit` value
- Try narrower viewer range
- Use `--dry-run` to test without database
- Check Twitch API status: https://devstatus.twitch.tv/

## Advanced Usage

### Automated Discovery (Cron Job)

Schedule regular discovery runs:

```bash
# crontab -e
# Run daily at 2 AM - discover Just Chatting streamers
0 2 * * * cd /path/to/-nxtup-newsletter && python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10 >> discovery.log 2>&1

# Run weekly on Mondays - discover gaming streamers
0 3 * * 1 cd /path/to/-nxtup-newsletter && python discover.py --game-id 21779 --min-viewers 50 --max-viewers 250 --limit 15 >> discovery.log 2>&1
```

### Bulk Discovery Script

Create a shell script to discover across multiple categories:

```bash
#!/bin/bash
# bulk_discover.sh

echo "Starting bulk streamer discovery..."

python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10
python discover.py --game-id 21779 --min-viewers 50 --max-viewers 250 --limit 10
python discover.py --game-id 27471 --min-viewers 50 --max-viewers 250 --limit 10
python discover.py --game-id 516575 --min-viewers 50 --max-viewers 250 --limit 10

echo "Bulk discovery complete"
echo "Total active streamers:"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM streamers WHERE is_active = true;"
```

### Track Discovery History

Monitor discovery effectiveness:

```sql
-- Streamers discovered per day
SELECT
    DATE(discovered_at) as discovery_date,
    COUNT(*) as streamers_added
FROM streamers
GROUP BY DATE(discovered_at)
ORDER BY discovery_date DESC;

-- Streamers by discovery source (can add a column for this)
SELECT
    COUNT(*) as total,
    AVG(EXTRACT(EPOCH FROM (NOW() - account_created_at)) / 86400)::int as avg_account_age_days
FROM streamers
WHERE discovered_at > NOW() - INTERVAL '7 days';
```

## Limitations

1. **No Historical Data**: Only finds currently live streamers
2. **Viewer Count Point-in-Time**: Based on viewers at discovery moment
3. **Manual Process**: Requires running script periodically
4. **No Automatic Re-discovery**: Doesn't update existing streamer profiles

## Future Enhancements

Potential improvements to the discovery utility:

- [ ] Multi-game batch discovery
- [ ] Filter by language or region
- [ ] Scheduled/automated discovery
- [ ] Track discovery source/reason
- [ ] Update existing streamer profiles
- [ ] Discovery metrics/analytics
- [ ] Integration with trending streamers API
- [ ] Discord/Slack notifications for discoveries

## See Also

- [Main README](README.md) - Project overview
- [Ingestion Service](ingestion/README.md) - Data collection service
- [Database Schema](schema/) - Database structure
- [Twitch API Documentation](https://dev.twitch.tv/docs/api/) - Official API docs

---

**Find the next generation of streaming talent** 🔍
