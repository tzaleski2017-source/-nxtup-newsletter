#!/usr/bin/env python3
"""
Twitch Analytics Aggregation Script

This script calculates 30-day rolling metrics for tracked streamers and populates
the streamer_statistics table. Designed to run daily as a cron job.

Key Features:
- SQL-heavy aggregation using CTEs for performance
- Idempotent operations with ON CONFLICT for safe re-runs
- CLI interface with date, streamer, and dry-run options
- Async operations with asyncpg

Usage:
    python analyze.py                           # Run for all active streamers, today's date
    python analyze.py --date 2024-03-15        # Run for specific date
    python analyze.py --streamer-id 12345      # Run for specific streamer
    python analyze.py --dry-run                # Preview without writing to database
"""

import argparse
import asyncio
import asyncpg
import logging
import sys
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# SQL query for calculating 30-day rolling metrics
# This query uses CTEs to perform all aggregation in the database for optimal performance
CALCULATE_METRICS_SQL = """
WITH date_bounds AS (
    -- Calculate the 30-day window boundaries
    SELECT
        ($2::DATE - INTERVAL '30 days')::TIMESTAMPTZ AS window_start,
        ($2::DATE + INTERVAL '1 day')::TIMESTAMPTZ AS window_end
),
relevant_broadcasts AS (
    -- Get all broadcasts within the 30-day window
    SELECT
        broadcast_id,
        started_at,
        ended_at,
        EXTRACT(EPOCH FROM (ended_at - started_at)) / 3600.0 AS duration_hours
    FROM broadcasts
    CROSS JOIN date_bounds
    WHERE streamer_id = $1
      AND started_at >= date_bounds.window_start
      AND started_at < date_bounds.window_end
      AND ended_at IS NOT NULL
),
broadcast_metrics AS (
    -- Aggregate broadcast-level metrics
    SELECT
        COUNT(*) AS total_broadcasts,
        COALESCE(SUM(duration_hours), 0) AS total_broadcast_hours,
        COALESCE(AVG(duration_hours), 0) AS avg_broadcast_duration
    FROM relevant_broadcasts
),
relevant_snapshots AS (
    -- Get all snapshots within the 30-day window
    SELECT
        bs.concurrent_viewers,
        bs.chat_messages_delta,
        bs.category_id,
        bs.follower_count
    FROM broadcast_snapshots bs
    CROSS JOIN date_bounds
    WHERE bs.streamer_id = $1
      AND bs.snapshot_timestamp >= date_bounds.window_start
      AND bs.snapshot_timestamp < date_bounds.window_end
),
snapshot_metrics AS (
    -- Aggregate snapshot-level metrics
    SELECT
        COALESCE(AVG(concurrent_viewers), 0) AS avg_concurrent_viewers,
        COALESCE(MAX(concurrent_viewers), 0) AS max_concurrent_viewers,
        COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY concurrent_viewers), 0) AS median_concurrent_viewers,
        -- Chat rate = total messages / (total viewer-hours / 4)
        -- Each snapshot = 15 minutes = 0.25 hours
        COALESCE(
            SUM(chat_messages_delta)::NUMERIC /
            NULLIF(SUM(concurrent_viewers) * 0.25, 0),
            0
        ) AS avg_chat_rate,
        COUNT(DISTINCT category_id) AS unique_categories,
        -- Follower gain/loss over the window
        CASE
            WHEN COUNT(*) > 0 THEN
                COALESCE(
                    (SELECT follower_count FROM relevant_snapshots ORDER BY follower_count DESC LIMIT 1) -
                    (SELECT follower_count FROM relevant_snapshots ORDER BY follower_count ASC LIMIT 1),
                    0
                )
            ELSE 0
        END AS follower_gain_30d,
        -- Latest follower count
        CASE
            WHEN COUNT(*) > 0 THEN
                (SELECT follower_count FROM relevant_snapshots ORDER BY follower_count DESC LIMIT 1)
            ELSE 0
        END AS latest_follower_count
    FROM relevant_snapshots
),
follower_velocity AS (
    -- Calculate follower velocity (rate of change)
    SELECT
        CASE
            WHEN snapshot_metrics.follower_gain_30d != 0 AND broadcast_metrics.total_broadcast_hours > 0 THEN
                snapshot_metrics.follower_gain_30d::NUMERIC / NULLIF(broadcast_metrics.total_broadcast_hours, 0)
            ELSE 0
        END AS velocity
    FROM snapshot_metrics, broadcast_metrics
)
-- Final aggregation combining all metrics
SELECT
    bm.total_broadcasts,
    bm.total_broadcast_hours,
    bm.avg_broadcast_duration,
    sm.avg_concurrent_viewers,
    sm.max_concurrent_viewers,
    sm.median_concurrent_viewers,
    sm.avg_chat_rate,
    sm.unique_categories,
    sm.follower_gain_30d,
    sm.latest_follower_count,
    fv.velocity AS follower_velocity
FROM broadcast_metrics bm, snapshot_metrics sm, follower_velocity fv;
"""


# SQL query for inserting statistics with idempotent conflict handling
INSERT_STATISTICS_SQL = """
INSERT INTO streamer_statistics (
    streamer_id,
    calculation_date,
    total_broadcasts,
    total_broadcast_hours,
    avg_broadcast_duration,
    avg_concurrent_viewers,
    max_concurrent_viewers,
    median_concurrent_viewers,
    avg_chat_rate,
    unique_categories,
    follower_gain_30d,
    follower_velocity,
    latest_follower_count,
    calculated_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW()
)
ON CONFLICT (streamer_id, calculation_date)
DO UPDATE SET
    total_broadcasts = EXCLUDED.total_broadcasts,
    total_broadcast_hours = EXCLUDED.total_broadcast_hours,
    avg_broadcast_duration = EXCLUDED.avg_broadcast_duration,
    avg_concurrent_viewers = EXCLUDED.avg_concurrent_viewers,
    max_concurrent_viewers = EXCLUDED.max_concurrent_viewers,
    median_concurrent_viewers = EXCLUDED.median_concurrent_viewers,
    avg_chat_rate = EXCLUDED.avg_chat_rate,
    unique_categories = EXCLUDED.unique_categories,
    follower_gain_30d = EXCLUDED.follower_gain_30d,
    follower_velocity = EXCLUDED.follower_velocity,
    latest_follower_count = EXCLUDED.latest_follower_count,
    updated_at = NOW();
"""


async def connect_database(database_url: str) -> asyncpg.Connection:
    """
    Connect to the PostgreSQL database.

    Args:
        database_url: PostgreSQL connection string

    Returns:
        asyncpg.Connection: Database connection
    """
    try:
        conn = await asyncpg.connect(database_url)
        logger.info("Successfully connected to database")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


async def get_active_streamers(conn: asyncpg.Connection) -> List[Dict[str, Any]]:
    """
    Fetch all active streamers from the database.

    Args:
        conn: Database connection

    Returns:
        List of streamer records with id, username, display_name
    """
    query = """
    SELECT streamer_id, username, display_name
    FROM streamers
    WHERE is_active = true
    ORDER BY streamer_id;
    """

    try:
        rows = await conn.fetch(query)
        streamers = [dict(row) for row in rows]
        logger.info(f"Found {len(streamers)} active streamers")
        return streamers
    except Exception as e:
        logger.error(f"Failed to fetch active streamers: {e}")
        raise


async def calculate_metrics_for_streamer(
    conn: asyncpg.Connection,
    streamer_id: int,
    calculation_date: date
) -> Optional[Dict[str, Any]]:
    """
    Calculate 30-day rolling metrics for a specific streamer.

    This function executes the SQL-heavy aggregation query that performs
    all calculations in the database for optimal performance.

    Args:
        conn: Database connection
        streamer_id: Twitch user ID
        calculation_date: Date for which to calculate metrics (end of 30-day window)

    Returns:
        Dictionary with calculated metrics, or None if no data available
    """
    try:
        row = await conn.fetchrow(CALCULATE_METRICS_SQL, streamer_id, calculation_date)

        if row is None:
            logger.warning(f"No data available for streamer {streamer_id}")
            return None

        # Convert Row to dict and format decimals
        metrics = dict(row)

        # Format numeric values for readability
        for key, value in metrics.items():
            if isinstance(value, Decimal):
                metrics[key] = float(value)

        return metrics

    except Exception as e:
        logger.error(f"Failed to calculate metrics for streamer {streamer_id}: {e}")
        raise


async def insert_statistics(
    conn: asyncpg.Connection,
    streamer_id: int,
    calculation_date: date,
    metrics: Dict[str, Any],
    dry_run: bool = False
) -> bool:
    """
    Insert calculated statistics into the streamer_statistics table.

    Uses ON CONFLICT to make the operation idempotent - safe to re-run
    multiple times for the same date.

    Args:
        conn: Database connection
        streamer_id: Twitch user ID
        calculation_date: Date for which metrics were calculated
        metrics: Dictionary of calculated metrics
        dry_run: If True, log but don't execute the insert

    Returns:
        True if successful, False otherwise
    """
    try:
        if dry_run:
            logger.info(f"[DRY RUN] Would insert statistics for streamer {streamer_id}:")
            logger.info(f"  Date: {calculation_date}")
            logger.info(f"  Broadcasts: {metrics['total_broadcasts']}")
            logger.info(f"  Avg Viewers: {metrics['avg_concurrent_viewers']:.2f}")
            logger.info(f"  Chat Rate: {metrics['avg_chat_rate']:.4f} msgs/viewer/hour")
            logger.info(f"  Follower Gain: {metrics['follower_gain_30d']}")
            logger.info(f"  Follower Velocity: {metrics['follower_velocity']:.2f} per hour")
            return True

        await conn.execute(
            INSERT_STATISTICS_SQL,
            streamer_id,
            calculation_date,
            int(metrics['total_broadcasts']),
            float(metrics['total_broadcast_hours']),
            float(metrics['avg_broadcast_duration']),
            float(metrics['avg_concurrent_viewers']),
            int(metrics['max_concurrent_viewers']),
            float(metrics['median_concurrent_viewers']),
            float(metrics['avg_chat_rate']),
            int(metrics['unique_categories']),
            int(metrics['follower_gain_30d']),
            float(metrics['follower_velocity']),
            int(metrics['latest_follower_count'])
        )

        logger.info(f"Successfully inserted statistics for streamer {streamer_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to insert statistics for streamer {streamer_id}: {e}")
        return False


async def process_streamer(
    conn: asyncpg.Connection,
    streamer_id: int,
    username: str,
    calculation_date: date,
    dry_run: bool = False
) -> bool:
    """
    Process a single streamer: calculate metrics and insert into database.

    Args:
        conn: Database connection
        streamer_id: Twitch user ID
        username: Streamer username (for logging)
        calculation_date: Date for which to calculate metrics
        dry_run: If True, preview without writing to database

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Processing streamer {username} (ID: {streamer_id})...")

    try:
        # Calculate metrics using SQL-heavy approach
        metrics = await calculate_metrics_for_streamer(conn, streamer_id, calculation_date)

        if metrics is None:
            logger.warning(f"No data available for {username}, skipping")
            return False

        # Check if there were any broadcasts in the window
        if metrics['total_broadcasts'] == 0:
            logger.info(f"No broadcasts in 30-day window for {username}, skipping")
            return False

        # Insert statistics with idempotent conflict handling
        success = await insert_statistics(
            conn, streamer_id, calculation_date, metrics, dry_run
        )

        return success

    except Exception as e:
        logger.error(f"Error processing streamer {username}: {e}")
        return False


async def main(
    database_url: str,
    calculation_date: Optional[date] = None,
    streamer_id: Optional[int] = None,
    dry_run: bool = False
):
    """
    Main orchestration function for analytics aggregation.

    Args:
        database_url: PostgreSQL connection string
        calculation_date: Date for which to calculate metrics (defaults to today)
        streamer_id: If provided, only process this streamer
        dry_run: If True, preview without writing to database
    """
    # Default to today if no date provided
    if calculation_date is None:
        calculation_date = date.today()

    logger.info("=" * 80)
    logger.info("Twitch Analytics Aggregation")
    logger.info("=" * 80)
    logger.info(f"Calculation Date: {calculation_date}")
    logger.info(f"30-Day Window: {calculation_date - timedelta(days=30)} to {calculation_date}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("=" * 80)

    conn = None
    try:
        # Connect to database
        conn = await connect_database(database_url)

        # Determine which streamers to process
        if streamer_id:
            # Process single streamer
            row = await conn.fetchrow(
                "SELECT streamer_id, username, display_name FROM streamers WHERE streamer_id = $1",
                streamer_id
            )

            if row is None:
                logger.error(f"Streamer ID {streamer_id} not found in database")
                return

            streamers = [dict(row)]
            logger.info(f"Processing single streamer: {row['username']}")
        else:
            # Process all active streamers
            streamers = await get_active_streamers(conn)

        if not streamers:
            logger.warning("No streamers to process")
            return

        # Process each streamer
        total = len(streamers)
        successful = 0
        failed = 0
        skipped = 0

        for i, streamer in enumerate(streamers, 1):
            logger.info(f"\n[{i}/{total}] " + "=" * 60)

            success = await process_streamer(
                conn,
                streamer['streamer_id'],
                streamer['username'],
                calculation_date,
                dry_run
            )

            if success:
                successful += 1
            elif success is False:
                skipped += 1
            else:
                failed += 1

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total Streamers: {total}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Skipped (no data): {skipped}")
        logger.info(f"Failed: {failed}")
        logger.info("=" * 80)

        if dry_run:
            logger.info("\nDRY RUN COMPLETE - No data was written to the database")

    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise
    finally:
        if conn:
            await conn.close()
            logger.info("Database connection closed")


def parse_date(date_string: str) -> date:
    """
    Parse date string in YYYY-MM-DD format.

    Args:
        date_string: Date in YYYY-MM-DD format

    Returns:
        date object

    Raises:
        argparse.ArgumentTypeError: If date format is invalid
    """
    try:
        return datetime.strptime(date_string, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_string}. Use YYYY-MM-DD")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calculate 30-day rolling analytics for Twitch streamers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Run for all active streamers, today's date
  %(prog)s --date 2024-03-15           # Run for specific date
  %(prog)s --streamer-id 12345         # Run for specific streamer
  %(prog)s --dry-run                   # Preview without writing to database
  %(prog)s --date 2024-03-15 --dry-run # Preview for specific date

Database Connection:
  Set DATABASE_URL environment variable or use --database-url option.
  Format: postgresql://user:password@host:port/database
        """
    )

    parser.add_argument(
        "--database-url",
        type=str,
        help="PostgreSQL connection string (or set DATABASE_URL env var)"
    )

    parser.add_argument(
        "--date",
        type=parse_date,
        default=None,
        help="Calculation date in YYYY-MM-DD format (default: today)"
    )

    parser.add_argument(
        "--streamer-id",
        type=int,
        default=None,
        help="Process only this streamer ID (default: all active streamers)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview calculations without writing to database"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Get database URL from args or environment
    import os
    database_url = args.database_url or os.getenv("DATABASE_URL")

    if not database_url:
        logger.error("Database URL not provided. Set DATABASE_URL environment variable or use --database-url")
        sys.exit(1)

    # Run async main
    try:
        asyncio.run(main(
            database_url=database_url,
            calculation_date=args.date,
            streamer_id=args.streamer_id,
            dry_run=args.dry_run
        ))
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
