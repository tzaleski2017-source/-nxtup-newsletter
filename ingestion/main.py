"""
Twitch Data Ingestion Service - Main Entry Point

Orchestrates all components:
- Database connection
- Twitch API authentication
- EventSub WebSocket (stream online/offline)
- IRC chat listener (message counting)
- Snapshot poller (15-minute metrics collection)
"""

import asyncio
import signal
import sys
from typing import List, Dict, Any

from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope

from config import get_settings
from database import initialize_database
from state import get_chat_manager
from twitch_eventsub import create_eventsub_handler
from twitch_chat import create_chat_listener
from poller import create_poller


class IngestionService:
    """
    Main application service that coordinates all components.

    Lifecycle:
        1. Initialize configuration
        2. Connect to database
        3. Authenticate with Twitch API
        4. Load tracked streamers from database
        5. Start EventSub handler (stream events)
        6. Start chat listener (IRC)
        7. Start snapshot poller (15-min schedule)
        8. Run until interrupted
        9. Graceful shutdown
    """

    def __init__(self):
        """Initialize service (configuration only)."""
        self.settings = get_settings()
        self.db = None
        self.chat_manager = None
        self.twitch = None
        self.eventsub = None
        self.chat_bot = None
        self.poller = None
        self.tracked_streamers: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        """
        Initialize all components.

        This method sets up connections and authenticates with external services.
        """
        print("=" * 80)
        print("Twitch Data Ingestion Service - Starting")
        print("=" * 80)

        # ====================================================================
        # 1. Initialize Database
        # ====================================================================
        print("\n[Init] Connecting to database...")
        self.db = initialize_database(self.settings.database_url)
        await self.db.connect()

        # Test connection
        if await self.db.health_check():
            print("[Init] ✓ Database connected and healthy")
        else:
            raise RuntimeError("Database health check failed")

        # ====================================================================
        # 2. Initialize Chat Counter Manager
        # ====================================================================
        self.chat_manager = get_chat_manager()
        print("[Init] ✓ Chat counter manager initialized")

        # ====================================================================
        # 3. Authenticate with Twitch API
        # ====================================================================
        print("\n[Init] Authenticating with Twitch API...")
        self.twitch = await Twitch(
            self.settings.twitch_client_id,
            self.settings.twitch_client_secret
        )

        # Set user authentication (required for EventSub)
        await self.twitch.set_user_authentication(
            token=self.settings.twitch_access_token,
            scope=[AuthScope.USER_READ_EMAIL],  # Minimal scope needed
            validate=True
        )

        print("[Init] ✓ Twitch API authenticated")

        # ====================================================================
        # 4. Load Tracked Streamers
        # ====================================================================
        print("\n[Init] Loading tracked streamers...")

        # Get streamers from database
        db_streamers = await self.db.get_tracked_streamers()

        if not db_streamers:
            print("[Init] Warning: No tracked streamers in database")
            print("[Init] Creating streamers from TRACKED_STREAMERS config...")

            # Fetch user data from Twitch and create records
            for username in self.settings.tracked_streamer_list:
                user_data = await self._get_user_by_username(username)
                if user_data:
                    await self.db.create_streamer(
                        streamer_id=user_data['id'],
                        username=user_data['login'],
                        display_name=user_data['display_name']
                    )
                    print(f"[Init]   → Created streamer: {username} (ID: {user_data['id']})")

            # Reload from database
            db_streamers = await self.db.get_tracked_streamers()

        self.tracked_streamers = db_streamers
        print(f"[Init] ✓ Tracking {len(self.tracked_streamers)} streamers:")
        for streamer in self.tracked_streamers:
            print(f"[Init]   - {streamer['username']} (ID: {streamer['streamer_id']})")

    async def _get_user_by_username(self, username: str) -> Dict[str, Any]:
        """
        Fetch user data from Twitch API by username.

        Args:
            username: Twitch username

        Returns:
            Dict with user data or None if not found
        """
        try:
            users = self.twitch.get_users(logins=[username])
            async for user in users:
                return {
                    'id': int(user.id),
                    'login': user.login,
                    'display_name': user.display_name
                }
            return None
        except Exception as e:
            print(f"[Init] Error fetching user {username}: {e}")
            return None

    async def start_components(self) -> None:
        """
        Start all service components.

        This method launches:
        - EventSub handler (stream online/offline)
        - Chat listener (IRC message counting)
        - Snapshot poller (15-minute metrics)
        """
        print("\n[Start] Launching service components...")

        # ====================================================================
        # 1. Start EventSub Handler
        # ====================================================================
        print("[Start] Starting EventSub handler...")
        self.eventsub = await create_eventsub_handler(
            twitch=self.twitch,
            database=self.db,
            chat_manager=self.chat_manager,
            tracked_streamers=self.tracked_streamers
        )
        print("[Start] ✓ EventSub handler running")

        # ====================================================================
        # 2. Start Chat Listener
        # ====================================================================
        print("[Start] Starting chat listener...")

        # Create message callback
        async def on_chat_message(channel_name: str):
            """Handle incoming chat message."""
            # Find streamer_id from username
            streamer = next(
                (s for s in self.tracked_streamers if s['username'].lower() == channel_name.lower()),
                None
            )

            if not streamer:
                return

            # Get active broadcast for this streamer
            broadcast = await self.db.get_broadcast_for_streamer(streamer['streamer_id'])

            if broadcast:
                # Increment chat counter
                await self.chat_manager.increment(broadcast['broadcast_id'])

        # Create chat listener
        channel_names = [s['username'] for s in self.tracked_streamers]
        self.chat_bot = await create_chat_listener(
            token=self.settings.twitch_access_token,
            channels=channel_names,
            on_message_callback=on_chat_message
        )

        # Start chat bot in background
        asyncio.create_task(self.chat_bot.start())
        print("[Start] ✓ Chat listener running")

        # Wait a moment for chat bot to connect
        await asyncio.sleep(2)

        # ====================================================================
        # 3. Start Snapshot Poller
        # ====================================================================
        print("[Start] Starting snapshot poller...")
        self.poller = create_poller(
            twitch=self.twitch,
            database=self.db,
            chat_manager=self.chat_manager,
            interval_minutes=self.settings.snapshot_interval_minutes
        )
        self.poller.start()
        print("[Start] ✓ Snapshot poller running")

    async def run(self) -> None:
        """
        Main run loop.

        Keeps the service running until interrupted by SIGINT or SIGTERM.
        """
        print("\n" + "=" * 80)
        print("🚀 Twitch Data Ingestion Service is RUNNING")
        print("=" * 80)
        print("\nMonitoring:")
        print(f"  • {len(self.tracked_streamers)} streamers")
        print(f"  • Stream events: stream.online, stream.offline")
        print(f"  • Chat messages: real-time counting")
        print(f"  • Snapshots: every {self.settings.snapshot_interval_minutes} minutes")
        print("\nPress Ctrl+C to stop")
        print("=" * 80 + "\n")

        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("\n[Main] Shutdown signal received")

    async def shutdown(self) -> None:
        """
        Graceful shutdown.

        Stops all components and closes connections.
        """
        print("\n[Shutdown] Stopping service...")

        # Stop poller
        if self.poller:
            self.poller.stop()
            print("[Shutdown] ✓ Poller stopped")

        # Stop EventSub
        if self.eventsub:
            await self.eventsub.stop()
            print("[Shutdown] ✓ EventSub stopped")

        # Chat bot will stop when event loop closes
        if self.chat_bot:
            print("[Shutdown] ✓ Chat listener stopped")

        # Close database
        if self.db:
            await self.db.close()
            print("[Shutdown] ✓ Database connection closed")

        print("[Shutdown] ✓ Shutdown complete")


async def main():
    """
    Application entry point.

    Handles:
    - Service initialization
    - Component startup
    - Signal handling (Ctrl+C)
    - Graceful shutdown
    """
    service = IngestionService()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        """Handle SIGINT and SIGTERM."""
        print(f"\n[Signal] Received signal {signum}")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize
        await service.initialize()

        # Start components
        await service.start_components()

        # Run until shutdown signal
        run_task = asyncio.create_task(service.run())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # Wait for shutdown signal or run task to complete
        done, pending = await asyncio.wait(
            [run_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()

    except KeyboardInterrupt:
        print("\n[Main] Interrupted by user")
    except Exception as e:
        print(f"\n[Main] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Always shutdown gracefully
        await service.shutdown()


if __name__ == "__main__":
    """
    Run the service.

    Usage:
        python -m ingestion.main

    Requirements:
        - .env file with configuration
        - Database schema already created
        - Twitch API credentials
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Main] Service stopped")
        sys.exit(0)
