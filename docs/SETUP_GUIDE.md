# Database Setup Guide - Step by Step

This guide walks through setting up the Twitch Analytics Platform database from scratch.

## Step 1: Create Neon Database

### 1.1 Sign Up for Neon

1. Go to [console.neon.tech](https://console.neon.tech)
2. Sign up with GitHub, Google, or email
3. Verify your email address

### 1.2 Create a New Project

1. Click "Create a project" in the Neon console
2. Project settings:
   - **Name**: `twitch-analytics` (or your preference)
   - **Region**: Choose closest to your location
   - **PostgreSQL version**: 16 (recommended) or latest
   - **Compute size**: 0.25 CU (free tier sufficient for testing)
3. Click "Create project"

### 1.3 Get Connection Details

After creation, Neon will show your connection string. It looks like:

```
postgresql://username:password@host.neon.tech/dbname?sslmode=require
```

**Save this securely** - you'll need it later.

## Step 2: Configure Neon MCP in Claude Code

### 2.1 MCP Configuration

The `.mcp.json` file has already been created in this project:

```json
{
  "mcpServers": {
    "neon": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote@latest",
        "https://mcp.neon.tech/mcp"
      ]
    }
  }
}
```

### 2.2 Restart Claude Code

1. **Close** your current Claude Code session
2. **Restart** Claude Code
3. When prompted, **authorize** the Neon MCP via OAuth
4. Select your `twitch-analytics` project

### 2.3 Verify MCP Connection

After restart, verify by asking Claude:

```
"List all tables in my Neon database"
```

If successful, Claude will use the Neon MCP to query your database (it should be empty initially).

## Step 3: Execute Database Schema

### Option A: Using Claude Code with Neon MCP

Simply ask Claude Code:

```
"Please execute the schema/setup.sql file to create all tables in my Neon database"
```

Claude will:
1. Read the schema files
2. Execute them in dependency order via Neon MCP
3. Verify tables were created
4. Show you the results

### Option B: Using psql (Command Line)

If you prefer manual execution:

```bash
# Navigate to project directory
cd /home/user/-nxtup-newsletter

# Execute setup script
psql "your_neon_connection_string" -f schema/setup.sql
```

### Option C: Using a Database GUI

1. **Download a PostgreSQL client**:
   - [pgAdmin](https://www.pgadmin.org/) (free, full-featured)
   - [DBeaver](https://dbeaver.io/) (free, multi-database)
   - [TablePlus](https://tableplus.com/) (paid, beautiful UI)
   - [Postico](https://eggerapps.at/postico/) (Mac only, paid)

2. **Connect to Neon**:
   - Host: Extract from your connection string
   - Port: 5432 (default)
   - Database: Extract from connection string
   - User: Extract from connection string
   - Password: Extract from connection string
   - SSL Mode: Require

3. **Execute Schema Files**:
   - Open and execute each `.sql` file in order:
     1. `01_streamers.sql`
     2. `02_categories.sql`
     3. `03_broadcasts.sql`
     4. `04_broadcast_snapshots.sql`
     5. `05_streamer_statistics.sql`

## Step 4: Verify Schema Installation

### 4.1 Check Tables Exist

Run this query in your database:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

**Expected output:**
```
 table_name
---------------------
 broadcasts
 broadcast_snapshots
 categories
 streamer_statistics
 streamers
```

### 4.2 Verify Foreign Keys

```sql
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
ORDER BY tc.table_name;
```

You should see relationships like:
- `broadcasts.streamer_id` → `streamers.streamer_id`
- `broadcasts.primary_category_id` → `categories.category_id`
- `broadcast_snapshots.broadcast_id` → `broadcasts.broadcast_id`
- etc.

### 4.3 Verify Indexes

```sql
SELECT
    tablename,
    indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

You should see multiple indexes per table (40+ total).

## Step 5: Load Sample Data

To test with realistic data:

```bash
psql "your_neon_connection_string" -f docs/sample_data.sql
```

Or using Claude Code:

```
"Please execute docs/sample_data.sql to load sample data"
```

### 5.1 Verify Sample Data

```sql
-- Check streamer count
SELECT COUNT(*) FROM streamers;  -- Should return 5

-- Check broadcast count
SELECT COUNT(*) FROM broadcasts;  -- Should return 8

-- Check snapshot count
SELECT COUNT(*) FROM broadcast_snapshots;  -- Should return 15
```

## Step 6: Test Analytical Queries

Run the example queries from `docs/example_queries.sql`:

```bash
psql "your_neon_connection_string" -f docs/example_queries.sql
```

Or copy individual queries and run them in your SQL client.

### 6.1 Quick Test Query

```sql
SELECT
    s.username,
    COUNT(b.broadcast_id) as broadcast_count,
    ROUND(AVG(bs.concurrent_viewers)::NUMERIC, 0) as avg_viewers
FROM streamers s
JOIN broadcasts b ON s.streamer_id = b.streamer_id
JOIN broadcast_snapshots bs ON b.broadcast_id = bs.broadcast_id
GROUP BY s.username
ORDER BY avg_viewers DESC;
```

**Expected output** (with sample data):
```
      username      | broadcast_count | avg_viewers
--------------------+-----------------+-------------
 hype_hunter_carol  |               3 |         361
 rising_bob         |               0 |           0
 hidden_gem_alice   |               9 |         163
```

## Step 7: Set Up Environment Variables (Recommended)

Instead of hardcoding connection strings, use environment variables:

### 7.1 Create .env file

```bash
# In project root
cat > .env << 'EOF'
NEON_CONNECTION_STRING=postgresql://user:pass@host.neon.tech/db?sslmode=require
NEON_HOST=your-host.neon.tech
NEON_DATABASE=your_database
NEON_USER=your_user
NEON_PASSWORD=your_password
EOF
```

### 7.2 Add .env to .gitignore

```bash
echo ".env" >> .gitignore
```

**CRITICAL**: Never commit `.env` files with credentials to version control!

## Step 8: Optional Enhancements

### 8.1 Enable Query Performance Tracking

```sql
-- Enable pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Check slow queries later
SELECT
    query,
    calls,
    mean_exec_time,
    max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### 8.2 Create Read-Only User (for reporting)

```sql
-- Create read-only role
CREATE ROLE readonly_user WITH LOGIN PASSWORD 'secure_password_here';
GRANT CONNECT ON DATABASE your_database TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- Auto-grant SELECT on future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO readonly_user;
```

### 8.3 Set Up Automated Backups

Neon provides automated backups, but you can also set up your own:

```bash
# Daily backup script (add to cron)
pg_dump "your_neon_connection_string" > backup_$(date +%Y%m%d).sql
```

## Troubleshooting

### Issue: "psql: command not found"

**Solution**: Install PostgreSQL client:

```bash
# Ubuntu/Debian
sudo apt-get install postgresql-client

# macOS
brew install postgresql

# Windows
# Download from https://www.postgresql.org/download/windows/
```

### Issue: "connection refused" or "could not connect"

**Solutions**:
1. Verify your connection string is correct
2. Check Neon project is not suspended (free tier suspends after inactivity)
3. Verify your IP is not blocked (check Neon IP allowlist settings)
4. Ensure `sslmode=require` is in connection string

### Issue: Neon MCP not showing up in Claude Code

**Solutions**:
1. Verify `.mcp.json` exists in project root
2. Completely restart Claude Code (not just reload)
3. Check Claude Code console for MCP loading errors
4. Try manual OAuth authentication in browser

### Issue: Tables already exist errors

**Solution**: Drop existing tables first:

```sql
-- WARNING: This deletes all data!
DROP TABLE IF EXISTS broadcast_snapshots CASCADE;
DROP TABLE IF EXISTS broadcasts CASCADE;
DROP TABLE IF EXISTS streamer_statistics CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS streamers CASCADE;

-- Then re-run setup.sql
```

### Issue: Permission denied creating tables

**Solution**: Ensure your Neon user has CREATE privileges:

```sql
-- Run as admin/owner
GRANT CREATE ON SCHEMA public TO your_username;
```

## Next Steps

After successful setup:

1. ✅ **Schema is ready** - Database tables created and verified
2. ✅ **Sample data loaded** - Test queries working
3. ⏭️ **Build data collection pipeline** - Start ingesting real Twitch data
4. ⏭️ **Develop ML models** - Train predictive models on collected data
5. ⏭️ **Create dashboard** - Visualize streamer metrics
6. ⏭️ **Automate newsletter** - Generate weekly/monthly curated lists

## Resources

- [Neon Documentation](https://neon.tech/docs)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Twitch API Documentation](https://dev.twitch.tv/docs/api/)
- [Neon MCP Server GitHub](https://github.com/neondatabase/mcp-server-neon)

---

**Congratulations!** Your Twitch Analytics Platform database is now ready for data collection.
