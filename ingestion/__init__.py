"""
Twitch Data Ingestion Pipeline

A hybrid polling and event-driven service for collecting Twitch streamer data.

Components:
- EventSub WebSocket: Real-time stream online/offline events
- IRC Chat Listener: Real-time chat message counting
- Snapshot Poller: Scheduled collection of viewership and follower metrics
- Database Writer: Persistent storage to PostgreSQL via Neon

Architecture:
- Single-process async application using asyncio
- In-memory state management for chat counters
- APScheduler for 15-minute snapshot intervals
"""

__version__ = "1.0.0"
