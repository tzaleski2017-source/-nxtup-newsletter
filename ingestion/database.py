"""
Database Operations

All database interactions using asyncpg for high-performance async PostgreSQL access.

Schema Alignment:
- broadcasts: schema/03_broadcasts.sql
- broadcast_snapshots: schema/04_broadcast_snapshots.sql
- streamers: schema/01_streamers.sql
"""

import asyncpg
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager


class Database:
    """
    Database connection pool and query operations.

    Uses asyncpg for async PostgreSQL access with connection pooling.
    All methods are designed to work with the existing schema.
    """

    def __init__(self, connection_string: str):
        """
        Initialize database with connection string.

        Args:
            connection_string: PostgreSQL connection URL
        """
        self.connection_string = connection_string
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """
        Create connection pool.

        Pool Configuration:
        - min_size=2: Maintain 2 connections always
        - max_size=10: Maximum 10 concurrent connections
        - command_timeout=60: Query timeout after 60 seconds
        """
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=2,
            max_size=10,
            command_timeout=60.0,
            # Enable SSL for Neon
            ssl='require'
        )
        print("[Database] Connection pool created")

    async def close(self) -> None:
        """Close connection pool gracefully."""
        if self.pool:
            await self.pool.close()
            print("[Database] Connection pool closed")

    @asynccontextmanager
    async def acquire(self):
        """Context manager for acquiring connection from pool."""
        async with self.pool.acquire() as connection:
            yield connection

    # =========================================================================
    # Streamer Operations
    # =========================================================================

    async def get_tracked_streamers(self) -> List[Dict[str, Any]]:
        """
        Get all active tracked streamers.

        Returns:
            List of dicts with 'streamer_id' and 'username' keys

        SQL:
            SELECT streamer_id, username
            FROM streamers
            WHERE is_active = true;
        """
        query = """
            SELECT streamer_id, username
            FROM streamers
            WHERE is_active = true
            ORDER BY username;
        """
        async with self.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def get_streamer_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get streamer by username.

        Args:
            username: Twitch username

        Returns:
            Dict with streamer data or None if not found
        """
        query = """
            SELECT streamer_id, username, display_name
            FROM streamers
            WHERE LOWER(username) = LOWER($1);
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(query, username)
            return dict(row) if row else None

    async def create_streamer(
        self,
        streamer_id: int,
        username: str,
        display_name: Optional[str] = None
    ) -> int:
        """
        Create new streamer record.

        Args:
            streamer_id: Twitch user ID
            username: Twitch username
            display_name: Display name with capitalization

        Returns:
            The streamer_id (same as input, for consistency)

        SQL:
            INSERT INTO streamers (streamer_id, username, display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (streamer_id) DO NOTHING;
        """
        query = """
            INSERT INTO streamers (streamer_id, username, display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (streamer_id) DO UPDATE
            SET username = EXCLUDED.username,
                display_name = EXCLUDED.display_name,
                updated_at = NOW();
        """
        async with self.acquire() as conn:
            await conn.execute(query, streamer_id, username, display_name or username)
        return streamer_id

    # =========================================================================
    # Broadcast Operations
    # =========================================================================

    async def create_broadcast(
        self,
        streamer_id: int,
        category_id: Optional[int],
        title: str,
        started_at: datetime
    ) -> int:
        """
        Create new broadcast record.

        Args:
            streamer_id: Twitch user ID
            category_id: Game/category ID (can be None)
            title: Stream title
            started_at: When stream started (UTC)

        Returns:
            broadcast_id: Auto-generated primary key

        SQL:
            INSERT INTO broadcasts (streamer_id, primary_category_id, stream_title, started_at)
            VALUES ($1, $2, $3, $4)
            RETURNING broadcast_id;
        """
        query = """
            INSERT INTO broadcasts (
                streamer_id,
                primary_category_id,
                stream_title,
                started_at
            )
            VALUES ($1, $2, $3, $4)
            RETURNING broadcast_id;
        """
        async with self.acquire() as conn:
            broadcast_id = await conn.fetchval(
                query,
                streamer_id,
                category_id,
                title,
                started_at
            )
        print(f"[Database] Created broadcast {broadcast_id} for streamer {streamer_id}")
        return broadcast_id

    async def get_active_broadcasts(self) -> List[Dict[str, Any]]:
        """
        Get all currently active broadcasts (ended_at IS NULL).

        Returns:
            List of dicts with broadcast data

        SQL:
            SELECT broadcast_id, streamer_id, started_at, primary_category_id
            FROM broadcasts
            WHERE ended_at IS NULL
            ORDER BY started_at ASC;
        """
        query = """
            SELECT
                broadcast_id,
                streamer_id,
                started_at,
                primary_category_id
            FROM broadcasts
            WHERE ended_at IS NULL
            ORDER BY started_at ASC;
        """
        async with self.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def get_broadcast_for_streamer(self, streamer_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the active broadcast for a specific streamer.

        Args:
            streamer_id: Twitch user ID

        Returns:
            Dict with broadcast data or None if no active broadcast

        SQL:
            SELECT broadcast_id, started_at, primary_category_id
            FROM broadcasts
            WHERE streamer_id = $1 AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1;
        """
        query = """
            SELECT
                broadcast_id,
                started_at,
                primary_category_id
            FROM broadcasts
            WHERE streamer_id = $1 AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1;
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(query, streamer_id)
            return dict(row) if row else None

    async def end_broadcast(self, broadcast_id: int, ended_at: datetime) -> None:
        """
        Mark broadcast as ended.

        Args:
            broadcast_id: Unique broadcast identifier
            ended_at: When stream ended (UTC)

        SQL:
            UPDATE broadcasts
            SET ended_at = $2,
                duration_seconds = EXTRACT(EPOCH FROM ($2 - started_at))::INTEGER,
                updated_at = NOW()
            WHERE broadcast_id = $1;
        """
        query = """
            UPDATE broadcasts
            SET
                ended_at = $2,
                duration_seconds = EXTRACT(EPOCH FROM ($2 - started_at))::INTEGER,
                updated_at = NOW()
            WHERE broadcast_id = $1;
        """
        async with self.acquire() as conn:
            result = await conn.execute(query, broadcast_id, ended_at)
        print(f"[Database] Ended broadcast {broadcast_id}")

    # =========================================================================
    # Snapshot Operations
    # =========================================================================

    async def create_snapshot(
        self,
        broadcast_id: int,
        streamer_id: int,
        category_id: Optional[int],
        timestamp: datetime,
        viewers: int,
        followers: int,
        chat_delta: int,
        uptime_seconds: int
    ) -> None:
        """
        Create broadcast snapshot.

        Args:
            broadcast_id: Broadcast identifier
            streamer_id: Streamer identifier (denormalized)
            category_id: Current game/category
            timestamp: Snapshot timestamp (UTC)
            viewers: Concurrent viewer count
            followers: Total follower count
            chat_delta: Messages since last snapshot
            uptime_seconds: Seconds since stream started

        SQL:
            INSERT INTO broadcast_snapshots (
                broadcast_id, streamer_id, category_id, snapshot_timestamp,
                concurrent_viewers, follower_count, chat_messages_delta, stream_uptime_seconds
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (broadcast_id, snapshot_timestamp) DO NOTHING;

        Note:
            ON CONFLICT prevents duplicate snapshots if job runs twice
        """
        query = """
            INSERT INTO broadcast_snapshots (
                broadcast_id,
                streamer_id,
                category_id,
                snapshot_timestamp,
                concurrent_viewers,
                follower_count,
                chat_messages_delta,
                stream_uptime_seconds
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (broadcast_id, snapshot_timestamp) DO NOTHING;
        """
        async with self.acquire() as conn:
            await conn.execute(
                query,
                broadcast_id,
                streamer_id,
                category_id,
                timestamp,
                viewers,
                followers,
                chat_delta,
                uptime_seconds
            )

    async def get_snapshot_count(self, broadcast_id: int) -> int:
        """
        Get total number of snapshots for a broadcast (for debugging).

        Args:
            broadcast_id: Broadcast identifier

        Returns:
            Number of snapshots
        """
        query = """
            SELECT COUNT(*)
            FROM broadcast_snapshots
            WHERE broadcast_id = $1;
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, broadcast_id)

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> bool:
        """
        Verify database connectivity.

        Returns:
            True if database is reachable, False otherwise
        """
        try:
            async with self.acquire() as conn:
                result = await conn.fetchval("SELECT 1;")
                return result == 1
        except Exception as e:
            print(f"[Database] Health check failed: {e}")
            return False


# Global singleton instance
_database: Optional[Database] = None


def get_database() -> Database:
    """Get the global database instance."""
    global _database
    if _database is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return _database


def initialize_database(connection_string: str) -> Database:
    """
    Initialize the global database instance.

    Args:
        connection_string: PostgreSQL connection URL

    Returns:
        Database instance
    """
    global _database
    _database = Database(connection_string)
    return _database
