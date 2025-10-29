"""
Twitch IRC Chat Listener

Real-time chat message counting using TwitchIO library.

Architecture:
- Connects to Twitch IRC servers
- Joins channels for tracked streamers
- Increments chat counters for each message
- Auto-reconnects on connection loss
"""

from twitchio.ext import commands
from typing import Callable, List, Dict, Any
import asyncio


class ChatListener(commands.Bot):
    """
    IRC bot that listens to Twitch chat and counts messages.

    This bot does not send messages or respond to commands. It purely
    listens to incoming messages and increments counters for analytics.

    Architecture Note:
        TwitchIO handles connection management, authentication, and
        automatic reconnection. We just need to implement event handlers.
    """

    def __init__(
        self,
        token: str,
        channels: List[str],
        on_message_callback: Callable[[str], Any]
    ):
        """
        Initialize chat listener.

        Args:
            token: Twitch access token (OAuth token)
            channels: List of channel names (usernames) to join
            on_message_callback: Async function called for each message
                                 with channel_name as argument
        """
        # Initialize parent Bot class
        super().__init__(
            token=token,
            prefix='!',  # Required but not used (we don't respond to commands)
            initial_channels=channels
        )
        self.on_message_callback = on_message_callback
        self.channels_to_track = set(channels)

        print(f"[ChatListener] Initialized for {len(channels)} channels: {', '.join(channels)}")

    async def event_ready(self):
        """
        Called when bot successfully connects to Twitch IRC.

        This is called once on startup and after any reconnection.
        """
        print(f"[ChatListener] Connected as {self.nick}")
        print(f"[ChatListener] Joined channels: {', '.join([c.name for c in self.connected_channels])}")

    async def event_message(self, message):
        """
        Called for every message in joined channels.

        Args:
            message: TwitchIO Message object with:
                - message.content: Message text
                - message.author: User who sent message
                - message.channel: Channel object
                - message.echo: True if this is our own message

        Note:
            We ignore echo messages (our own messages, though we don't send any)
            and only count messages from tracked channels.
        """
        # Ignore bot's own messages
        if message.echo:
            return

        # Get channel name
        channel_name = message.channel.name

        # Only process messages from channels we're tracking
        if channel_name not in self.channels_to_track:
            return

        # Call the callback to increment counter
        try:
            # The callback is async, so we await it
            if asyncio.iscoroutinefunction(self.on_message_callback):
                await self.on_message_callback(channel_name)
            else:
                self.on_message_callback(channel_name)
        except Exception as e:
            print(f"[ChatListener] Error in message callback for {channel_name}: {e}")

    async def event_error(self, error: Exception, data: str = None):
        """
        Called when an error occurs.

        Args:
            error: The exception that occurred
            data: Additional error data (if available)
        """
        print(f"[ChatListener] Error: {error}")
        if data:
            print(f"[ChatListener] Error data: {data}")

    async def event_reconnect(self):
        """Called when bot is attempting to reconnect."""
        print("[ChatListener] Reconnecting to Twitch IRC...")

    def add_channels(self, channels: List[str]):
        """
        Add additional channels to track (for dynamic streamer addition).

        Args:
            channels: List of channel names to add
        """
        self.channels_to_track.update(channels)
        # Join the channels
        for channel in channels:
            asyncio.create_task(self.join_channels([channel]))

    def remove_channels(self, channels: List[str]):
        """
        Remove channels from tracking (for dynamic streamer removal).

        Args:
            channels: List of channel names to remove
        """
        self.channels_to_track.difference_update(channels)
        # Part (leave) the channels
        for channel in channels:
            asyncio.create_task(self.part_channels([channel]))


async def create_chat_listener(
    token: str,
    channels: List[str],
    on_message_callback: Callable[[str], Any]
) -> ChatListener:
    """
    Factory function to create and start chat listener.

    Args:
        token: Twitch access token
        channels: Channel names to join
        on_message_callback: Callback function for messages

    Returns:
        Initialized and connected ChatListener instance

    Usage:
        >>> async def handle_message(channel: str):
        ...     print(f"Message in {channel}")
        >>>
        >>> listener = await create_chat_listener(
        ...     token="oauth:...",
        ...     channels=["streamer1", "streamer2"],
        ...     on_message_callback=handle_message
        ... )
    """
    listener = ChatListener(
        token=token,
        channels=channels,
        on_message_callback=on_message_callback
    )

    # Start the bot (this runs in background)
    # Note: The bot.start() method handles the event loop internally
    return listener
