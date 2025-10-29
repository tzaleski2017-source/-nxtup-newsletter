"""
Snapshot Polling Service

Scheduled collection of broadcast metrics every 15 minutes.

This is the core data collection component that:
1. Fetches current viewer counts from Twitch API
2. Fetches current follower counts from Twitch API
3. Reads and resets chat message counters
4. Writes complete snapshots to the database
"""

import asyncio
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from twitchAPI.twitch import Twitch
from typing import Dict, Any, List


class SnapshotPoller:
    """
    Polls Twitch API every 15 minutes to collect broadcast snapshots.

    Architecture:
        Uses APScheduler to run on a cron schedule (0, 15, 30, 45 minutes).
        For each active broadcast:
        1. Calls Twitch Helix API for current stream data
        2. Reads and resets the chat message counter
        3. Calculates stream uptime
        4. Inserts snapshot into database

    The 15-minute interval is critical:
        - Aligns with the schema design (chat_messages_delta is per-interval)
        - Provides sufficient granularity for engagement analysis
        - Stays well within Twitch API rate limits
    """

    def __init__(
        self,
        twitch: Twitch,
        database,
        chat_manager,
        interval_minutes: int = 15
    ):
        """
        Initialize snapshot poller.

        Args:
            twitch: Authenticated Twitch API client
            database: Database instance
            chat_manager: ChatCounterManager instance
            interval_minutes: Polling interval (default: 15)
        """
        self.twitch = twitch
        self.db = database
        self.chat = chat_manager
        self.interval_minutes = interval_minutes
        self.scheduler = AsyncIOScheduler()

        print(f"[Poller] Initialized with {interval_minutes}-minute interval")

    def start(self) -> None:
        """
        Start the scheduler.

        Schedule:
            Runs at 0, 15, 30, and 45 minutes past each hour.
            Example: 10:00, 10:15, 10:30, 10:45, 11:00, ...
        """
        # Add job with cron trigger
        self.scheduler.add_job(
            self.collect_snapshots,
            'cron',
            minute=f'*/{self.interval_minutes}',  # Every N minutes
            id='snapshot_collector',
            name='Broadcast Snapshot Collection',
            misfire_grace_time=60  # Allow 60 seconds grace if job delayed
        )

        # Start scheduler
        self.scheduler.start()
        print(f"[Poller] ✓ Started (runs every {self.interval_minutes} minutes)")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            print("[Poller] Stopped")

    async def collect_snapshots(self) -> None:
        """
        Main snapshot collection logic.

        This method is called every 15 minutes by the scheduler.

        Flow:
            1. Get all active broadcasts from database
            2. For each broadcast, collect snapshot data in parallel
            3. Write snapshots to database
            4. Log results
        """
        try:
            print(f"\n[Poller] === Starting snapshot collection at {datetime.now(timezone.utc).isoformat()} ===")

            # Get all active broadcasts
            broadcasts = await self.db.get_active_broadcasts()

            if not broadcasts:
                print("[Poller] No active broadcasts to snapshot")
                return

            print(f"[Poller] Found {len(broadcasts)} active broadcast(s)")

            # Collect snapshots in parallel for efficiency
            tasks = [
                self._snapshot_broadcast(broadcast)
                for broadcast in broadcasts
            ]

            # Wait for all snapshots to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes and failures
            successes = sum(1 for r in results if r is True)
            failures = sum(1 for r in results if r is not True)

            print(f"[Poller] === Snapshot collection complete: {successes} success, {failures} failed ===\n")

        except Exception as e:
            print(f"[Poller] Error in snapshot collection: {e}")
            import traceback
            traceback.print_exc()

    async def _snapshot_broadcast(self, broadcast: Dict[str, Any]) -> bool:
        """
        Collect snapshot for a single broadcast.

        Args:
            broadcast: Dict with keys:
                - broadcast_id: Unique identifier
                - streamer_id: Streamer's user ID
                - started_at: When stream started
                - primary_category_id: Primary game/category

        Returns:
            True if successful, False otherwise

        Critical Flow:
            1. Get current stream data (viewers, game) from Twitch API
            2. Get current follower count from Twitch API
            3. Read and RESET chat counter (this is the delta for this interval)
            4. Calculate stream uptime
            5. Insert snapshot into database
        """
        broadcast_id = broadcast['broadcast_id']
        streamer_id = broadcast['streamer_id']
        started_at = broadcast['started_at']

        try:
            # ================================================================
            # STEP 1: Get current stream data from Twitch
            # ================================================================
            stream_data = await self._get_stream_data(streamer_id)

            if not stream_data:
                # Stream ended but database not yet updated
                print(f"[Poller] Warning: Broadcast {broadcast_id} appears offline (skipping)")
                return False

            concurrent_viewers = stream_data['viewer_count']
            category_id = stream_data['game_id']

            # ================================================================
            # STEP 2: Get current follower count
            # ================================================================
            follower_count = await self._get_follower_count(streamer_id)

            # ================================================================
            # STEP 3: Read and reset chat counter
            # ================================================================
            # CRITICAL: This is the chat_messages_delta for this 15-min window
            chat_delta = await self.chat.read_and_reset(broadcast_id)

            # ================================================================
            # STEP 4: Calculate stream uptime
            # ================================================================
            now = datetime.now(timezone.utc)
            uptime_seconds = int((now - started_at).total_seconds())

            # ================================================================
            # STEP 5: Insert snapshot into database
            # ================================================================
            await self.db.create_snapshot(
                broadcast_id=broadcast_id,
                streamer_id=streamer_id,
                category_id=category_id,
                timestamp=now,
                viewers=concurrent_viewers,
                followers=follower_count,
                chat_delta=chat_delta,
                uptime_seconds=uptime_seconds
            )

            print(
                f"[Poller] ✓ Snapshot {broadcast_id}: "
                f"{concurrent_viewers} viewers, {chat_delta} messages, "
                f"{follower_count} followers"
            )

            return True

        except Exception as e:
            print(f"[Poller] ✗ Failed to snapshot broadcast {broadcast_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _get_stream_data(self, streamer_id: int) -> Dict[str, Any]:
        """
        Get current stream data from Twitch Helix API.

        Args:
            streamer_id: Twitch user ID

        Returns:
            Dict with keys:
                - viewer_count: Current concurrent viewers
                - game_id: Current game/category ID (int or None)
                - started_at: Stream start time
                - title: Stream title
            Or None if stream is offline

        API Call:
            GET https://api.twitch.tv/helix/streams?user_id={streamer_id}
        """
        try:
            # Get stream data
            streams = self.twitch.get_streams(user_id=[str(streamer_id)])

            # Iterate to get first (and only) result
            async for stream in streams:
                return {
                    'viewer_count': stream.viewer_count,
                    'game_id': int(stream.game_id) if stream.game_id else None,
                    'started_at': stream.started_at,
                    'title': stream.title
                }

            # No stream found (offline)
            return None

        except Exception as e:
            print(f"[Poller] Error fetching stream data for {streamer_id}: {e}")
            return None

    async def _get_follower_count(self, streamer_id: int) -> int:
        """
        Get total follower count for a streamer.

        Args:
            streamer_id: Twitch user ID

        Returns:
            Total number of followers

        API Call:
            GET https://api.twitch.tv/helix/channels/followers?broadcaster_id={streamer_id}

        Note:
            This returns only the total count (not the list of followers).
            The API endpoint automatically returns pagination info including total.
        """
        try:
            # Get followers (we only need the total count)
            followers = await self.twitch.get_channel_followers(
                broadcaster_id=str(streamer_id)
            )

            # The pagination object has a 'total' attribute
            return followers.total if followers else 0

        except Exception as e:
            print(f"[Poller] Error fetching follower count for {streamer_id}: {e}")
            # Return 0 as fallback (better than failing entire snapshot)
            return 0

    async def run_once_now(self) -> None:
        """
        Run snapshot collection immediately (for testing/manual trigger).

        This bypasses the scheduler and runs collection right now.
        Useful for:
        - Testing the poller without waiting 15 minutes
        - Manual data backfill
        - Debugging
        """
        print("[Poller] Running snapshot collection NOW (manual trigger)")
        await self.collect_snapshots()


def create_poller(
    twitch: Twitch,
    database,
    chat_manager,
    interval_minutes: int = 15
) -> SnapshotPoller:
    """
    Factory function to create snapshot poller.

    Args:
        twitch: Authenticated Twitch API client
        database: Database instance
        chat_manager: ChatCounterManager instance
        interval_minutes: Polling interval (default: 15)

    Returns:
        SnapshotPoller instance (not yet started)

    Usage:
        >>> poller = create_poller(twitch, db, chat_manager)
        >>> poller.start()  # Start the scheduler
        >>> # ... application runs ...
        >>> poller.stop()   # Stop the scheduler
    """
    return SnapshotPoller(twitch, database, chat_manager, interval_minutes)
