"""
Twitch EventSub WebSocket Handler

Real-time event notifications for stream online/offline events.

Uses pyTwitchAPI's EventSub WebSocket transport (no public endpoint needed).
"""

from twitchAPI.twitch import Twitch
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.object.eventsub import (
    StreamOnlineEvent,
    StreamOfflineEvent
)
from typing import List, Dict, Any
from datetime import datetime, timezone
import asyncio


class EventSubHandler:
    """
    Handles Twitch EventSub events via WebSocket transport.

    Events Handled:
    - stream.online: When a tracked streamer goes live
    - stream.offline: When a tracked streamer ends their stream

    Architecture:
        The WebSocket transport automatically handles:
        - Connection management
        - Reconnection on disconnect
        - Event subscription lifecycle
        - Message verification
    """

    def __init__(
        self,
        twitch: Twitch,
        database,
        chat_manager,
        tracked_streamers: List[Dict[str, Any]]
    ):
        """
        Initialize EventSub handler.

        Args:
            twitch: Authenticated Twitch API client
            database: Database instance for storing broadcasts
            chat_manager: ChatCounterManager for initializing/removing counters
            tracked_streamers: List of dicts with 'streamer_id' and 'username'
        """
        self.twitch = twitch
        self.db = database
        self.chat = chat_manager
        self.tracked_streamers = tracked_streamers
        self.eventsub: EventSubWebsocket = None

        print(f"[EventSub] Initialized for {len(tracked_streamers)} streamers")

    async def start(self) -> None:
        """
        Start EventSub WebSocket connection and subscribe to events.

        This method:
        1. Creates WebSocket connection
        2. Subscribes to stream.online and stream.offline for each streamer
        3. Starts listening for events
        """
        try:
            # Create EventSub WebSocket instance
            self.eventsub = EventSubWebsocket(self.twitch)

            # Start the WebSocket connection
            self.eventsub.start()
            print("[EventSub] WebSocket connection started")

            # Wait a moment for connection to establish
            await asyncio.sleep(2)

            # Subscribe to events for each tracked streamer
            for streamer in self.tracked_streamers:
                streamer_id = str(streamer['streamer_id'])
                username = streamer['username']

                try:
                    # Subscribe to stream.online event
                    await self.eventsub.listen_stream_online(
                        broadcaster_user_id=streamer_id,
                        callback=self.on_stream_online
                    )

                    # Subscribe to stream.offline event
                    await self.eventsub.listen_stream_offline(
                        broadcaster_user_id=streamer_id,
                        callback=self.on_stream_offline
                    )

                    print(f"[EventSub] Subscribed to events for {username} ({streamer_id})")

                except Exception as e:
                    print(f"[EventSub] Failed to subscribe for {username}: {e}")

            print(f"[EventSub] ✓ Listening for events from {len(self.tracked_streamers)} streamers")

        except Exception as e:
            print(f"[EventSub] Failed to start: {e}")
            raise

    async def stop(self) -> None:
        """Stop EventSub WebSocket connection gracefully."""
        if self.eventsub:
            try:
                await self.eventsub.stop()
                print("[EventSub] WebSocket connection stopped")
            except Exception as e:
                print(f"[EventSub] Error stopping: {e}")

    async def on_stream_online(self, data: StreamOnlineEvent) -> None:
        """
        Handle stream.online event.

        This is called when a tracked streamer goes live.

        Args:
            data: StreamOnlineEvent object containing:
                - broadcaster_user_id: Streamer's user ID
                - broadcaster_user_name: Streamer's username
                - broadcaster_user_login: Streamer's login name
                - type: Stream type ("live", "playlist", "watch_party", etc.)
                - started_at: When stream started (datetime)

        Flow:
            1. Extract streamer_id and started_at
            2. Get additional stream details (title, game) from Helix API
            3. Create broadcast record in database
            4. Initialize chat counter for this broadcast
        """
        try:
            event = data.event
            streamer_id = int(event.broadcaster_user_id)
            username = event.broadcaster_user_login
            started_at = event.started_at

            print(f"[EventSub] 🔴 Stream ONLINE: {username} (ID: {streamer_id})")

            # Get additional stream details from Helix API
            # (EventSub doesn't include title, game, etc.)
            stream_data = None
            try:
                streams = self.twitch.get_streams(user_id=[str(streamer_id)])
                async for stream in streams:
                    stream_data = stream
                    break
            except Exception as e:
                print(f"[EventSub] Warning: Could not fetch stream details: {e}")

            # Extract data with fallbacks
            if stream_data:
                title = stream_data.title or "Untitled Stream"
                category_id = int(stream_data.game_id) if stream_data.game_id else None
            else:
                title = "Untitled Stream"
                category_id = None

            # Create broadcast record in database
            broadcast_id = await self.db.create_broadcast(
                streamer_id=streamer_id,
                category_id=category_id,
                title=title,
                started_at=started_at
            )

            # Initialize chat counter
            await self.chat.initialize(broadcast_id)

            print(f"[EventSub] ✓ Created broadcast {broadcast_id} for {username}")

        except Exception as e:
            print(f"[EventSub] Error handling stream.online: {e}")
            import traceback
            traceback.print_exc()

    async def on_stream_offline(self, data: StreamOfflineEvent) -> None:
        """
        Handle stream.offline event.

        This is called when a tracked streamer's stream ends.

        Args:
            data: StreamOfflineEvent object containing:
                - broadcaster_user_id: Streamer's user ID
                - broadcaster_user_name: Streamer's username
                - broadcaster_user_login: Streamer's login name

        Flow:
            1. Extract streamer_id
            2. Find active broadcast for this streamer
            3. Update broadcast with ended_at timestamp
            4. Remove chat counter for this broadcast
        """
        try:
            event = data.event
            streamer_id = int(event.broadcaster_user_id)
            username = event.broadcaster_user_login

            print(f"[EventSub] ⚫ Stream OFFLINE: {username} (ID: {streamer_id})")

            # Find active broadcast for this streamer
            broadcast = await self.db.get_broadcast_for_streamer(streamer_id)

            if not broadcast:
                print(f"[EventSub] Warning: No active broadcast found for {username}")
                return

            broadcast_id = broadcast['broadcast_id']

            # Update broadcast with end time
            ended_at = datetime.now(timezone.utc)
            await self.db.end_broadcast(
                broadcast_id=broadcast_id,
                ended_at=ended_at
            )

            # Remove chat counter (cleanup)
            await self.chat.remove(broadcast_id)

            print(f"[EventSub] ✓ Ended broadcast {broadcast_id} for {username}")

        except Exception as e:
            print(f"[EventSub] Error handling stream.offline: {e}")
            import traceback
            traceback.print_exc()


async def create_eventsub_handler(
    twitch: Twitch,
    database,
    chat_manager,
    tracked_streamers: List[Dict[str, Any]]
) -> EventSubHandler:
    """
    Factory function to create and start EventSub handler.

    Args:
        twitch: Authenticated Twitch API client
        database: Database instance
        chat_manager: ChatCounterManager instance
        tracked_streamers: List of tracked streamer dicts

    Returns:
        Started EventSubHandler instance
    """
    handler = EventSubHandler(twitch, database, chat_manager, tracked_streamers)
    await handler.start()
    return handler
