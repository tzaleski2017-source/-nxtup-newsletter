-- ============================================================================
-- Twitch Analytics Platform - Complete Database Setup Script
-- ============================================================================
-- Purpose: Execute all schema definitions in correct dependency order
-- Usage: Execute this file against your Neon PostgreSQL database
-- ============================================================================
-- Prerequisites:
--   1. Neon PostgreSQL database created
--   2. Connection credentials configured
--   3. Appropriate CREATE privileges
-- ============================================================================

\echo '============================================================================'
\echo 'Twitch Analytics Platform - Database Schema Setup'
\echo '============================================================================'
\echo ''

-- Enable timing to monitor performance
\timing on

-- Abort on error
\set ON_ERROR_STOP on

-- ============================================================================
-- STEP 1: Create Base Tables (No Dependencies)
-- ============================================================================

\echo '>>> Step 1/5: Creating streamers table...'
\i 01_streamers.sql
\echo '✓ Streamers table created successfully'
\echo ''

\echo '>>> Step 2/5: Creating categories table...'
\i 02_categories.sql
\echo '✓ Categories table created successfully'
\echo ''

-- ============================================================================
-- STEP 2: Create Dependent Tables
-- ============================================================================

\echo '>>> Step 3/5: Creating broadcasts table...'
\i 03_broadcasts.sql
\echo '✓ Broadcasts table created successfully'
\echo ''

\echo '>>> Step 4/5: Creating broadcast_snapshots table...'
\i 04_broadcast_snapshots.sql
\echo '✓ Broadcast snapshots table created successfully'
\echo ''

\echo '>>> Step 5/5: Creating streamer_statistics table...'
\i 05_streamer_statistics.sql
\echo '✓ Streamer statistics table created successfully'
\echo ''

-- ============================================================================
-- STEP 3: Verification
-- ============================================================================

\echo '============================================================================'
\echo 'Verification: Listing all created tables'
\echo '============================================================================'

SELECT
    table_name,
    pg_size_pretty(pg_total_relation_size(quote_ident(table_name)::regclass)) as size
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

\echo ''
\echo '============================================================================'
\echo 'Verification: Foreign Key Constraints'
\echo '============================================================================'

SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
    AND ccu.table_schema = tc.table_schema
JOIN information_schema.referential_constraints AS rc
    ON tc.constraint_name = rc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
ORDER BY tc.table_name, kcu.column_name;

\echo ''
\echo '============================================================================'
\echo 'Verification: Indexes'
\echo '============================================================================'

SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

\echo ''
\echo '============================================================================'
\echo 'Database Schema Setup Complete!'
\echo '============================================================================'
\echo ''
\echo 'Next Steps:'
\echo '  1. Review the verification output above'
\echo '  2. Test with sample data (see ../docs/sample_data.sql)'
\echo '  3. Run analytical queries (see ../docs/example_queries.sql)'
\echo '  4. Set up data collection pipeline'
\echo ''
\echo '============================================================================'

\timing off
