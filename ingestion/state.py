"""
Shared State Management

Thread-safe in-memory storage for chat message counters.

Architecture Note:
This uses a simple dict with asyncio.Lock for the MVP. For production horizontal
scaling, migrate to Redis with the following structure:
  - Key: "chat_counter:{broadcast_id}"
  - Value: integer count
  - Operations: INCR, GETDEL (get and delete atomically)
"""

import asyncio
from typing import Dict, Optional


class ChatCounterManager:
    """
    Thread-safe manager for chat message counters.

    Each active broadcast has an associated counter that tracks the number of
    chat messages received since the last snapshot. When the poller runs every
    15 minutes, it reads and resets these counters.

    Thread Safety:
        All operations use asyncio.Lock to prevent race conditions between
        the chat listener (incrementing) and the poller (reading/resetting).
    """

    def __init__(self):
        """Initialize counter storage and lock."""
        self.counters: Dict[int, int] = {}  # {broadcast_id: message_count}
        self.lock = asyncio.Lock()

    async def initialize(self, broadcast_id: int) -> None:
        """
        Initialize counter to zero for a new broadcast.

        Args:
            broadcast_id: Unique identifier for the broadcast
        """
        async with self.lock:
            if broadcast_id not in self.counters:
                self.counters[broadcast_id] = 0
                print(f"[ChatCounter] Initialized counter for broadcast {broadcast_id}")

    async def increment(self, broadcast_id: int, amount: int = 1) -> None:
        """
        Increment message counter for a broadcast.

        Args:
            broadcast_id: Unique identifier for the broadcast
            amount: Number to increment by (default: 1)
        """
        async with self.lock:
            self.counters[broadcast_id] = self.counters.get(broadcast_id, 0) + amount

    async def read_and_reset(self, broadcast_id: int) -> int:
        """
        Read current count and reset to zero atomically.

        This is called by the snapshot poller to get the chat_messages_delta
        for the current 15-minute window.

        Args:
            broadcast_id: Unique identifier for the broadcast

        Returns:
            The count before reset (0 if broadcast_id not found)
        """
        async with self.lock:
            count = self.counters.get(broadcast_id, 0)
            self.counters[broadcast_id] = 0
            return count

    async def remove(self, broadcast_id: int) -> None:
        """
        Remove counter for ended broadcast (cleanup).

        Args:
            broadcast_id: Unique identifier for the broadcast
        """
        async with self.lock:
            removed_count = self.counters.pop(broadcast_id, None)
            if removed_count is not None:
                print(f"[ChatCounter] Removed counter for broadcast {broadcast_id} (final count: {removed_count})")

    async def get_count(self, broadcast_id: int) -> Optional[int]:
        """
        Get current count without resetting (for debugging).

        Args:
            broadcast_id: Unique identifier for the broadcast

        Returns:
            Current count or None if not found
        """
        async with self.lock:
            return self.counters.get(broadcast_id)

    async def get_all_active(self) -> Dict[int, int]:
        """
        Get all active broadcast counters (for debugging/monitoring).

        Returns:
            Copy of all counters
        """
        async with self.lock:
            return self.counters.copy()


# Global singleton instance
_chat_manager: Optional[ChatCounterManager] = None


def get_chat_manager() -> ChatCounterManager:
    """Get or create the global chat counter manager."""
    global _chat_manager
    if _chat_manager is None:
        _chat_manager = ChatCounterManager()
    return _chat_manager
