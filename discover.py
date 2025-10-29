#!/usr/bin/env python3
"""
Twitch Streamer Discovery Utility

A command-line tool to discover and add new Twitch streamers to the tracking database.

Usage:
    python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10

This script:
1. Searches Twitch for live streams in a specific game/category
2. Filters streams by concurrent viewer count
3. Checks if streamers already exist in the database
4. Adds new streamers to the database for tracking

Requirements:
    - TWITCH_CLIENT_ID environment variable
    - TWITCH_CLIENT_SECRET environment variable
    - DATABASE_URL environment variable
"""

import asyncio
import argparse
import os
import sys
from typing import Dict, Optional, Tuple
from datetime import datetime

import asyncpg
from twitchAPI.twitch import Twitch
from dotenv import load_dotenv


# ============================================================================
# Helper Functions
# ============================================================================

async def check_streamer_exists(conn: asyncpg.Connection, streamer_id: int) -> bool:
    """
    Check if streamer already exists in database.

    Args:
        conn: asyncpg database connection
        streamer_id: Twitch user ID (as integer)

    Returns:
        True if streamer exists, False otherwise
    """
    result = await conn.fetchval(
        "SELECT 1 FROM streamers WHERE streamer_id = $1",
        streamer_id
    )
    return result is not None


async def insert_streamer(
    conn: asyncpg.Connection,
    streamer_id: int,
    username: str,
    display_name: str,
    profile_image_url: str,
    description: str,
    account_created_at: datetime
) -> None:
    """
    Insert new streamer into database.

    Args:
        conn: asyncpg database connection
        streamer_id: Twitch user ID
        username: Twitch username (lowercase)
        display_name: Display name (with capitalization)
        profile_image_url: Profile image URL
        description: Channel description
        account_created_at: When Twitch account was created

    Note:
        Uses ON CONFLICT DO NOTHING to handle race conditions.
        Sets is_active = true for newly discovered streamers.
    """
    await conn.execute(
        """
        INSERT INTO streamers (
            streamer_id,
            username,
            display_name,
            profile_image_url,
            description,
            account_created_at,
            is_active
        ) VALUES ($1, $2, $3, $4, $5, $6, true)
        ON CONFLICT (streamer_id) DO NOTHING;
        """,
        streamer_id,
        username,
        display_name,
        profile_image_url if profile_image_url else None,
        description if description else None,
        account_created_at
    )


async def get_twitch_user_data(twitch: Twitch, user_id: str) -> Optional[Dict]:
    """
    Fetch full user profile from Twitch API.

    Args:
        twitch: Authenticated Twitch API client
        user_id: Twitch user ID (as string)

    Returns:
        Dict with user data or None if not found
    """
    try:
        users = twitch.get_users(user_ids=[user_id])

        # Get first (and only) result
        async for user in users:
            return {
                'id': int(user.id),  # Convert string to int
                'login': user.login,
                'display_name': user.display_name,
                'profile_image_url': user.profile_image_url,
                'description': user.description,
                'created_at': user.created_at
            }

        return None
    except Exception as e:
        print(f"  ✗ Error fetching user data: {e}")
        return None


# ============================================================================
# Main Discovery Logic
# ============================================================================

async def discover_streamers(
    game_id: str,
    min_viewers: int,
    max_viewers: int,
    limit: int,
    dry_run: bool = False
) -> Tuple[int, int, int]:
    """
    Discover and add new streamers matching criteria.

    Args:
        game_id: Twitch game/category ID
        min_viewers: Minimum concurrent viewers
        max_viewers: Maximum concurrent viewers
        limit: Maximum number of streamers to add
        dry_run: If True, don't make database changes

    Returns:
        Tuple of (processed_count, skipped_count, added_count)
    """
    # Load environment variables
    load_dotenv()

    twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
    database_url = os.getenv('DATABASE_URL')

    # Validate environment variables
    if not twitch_client_id or not twitch_client_secret:
        print("✗ Error: TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set")
        print("  Check your .env file or environment variables")
        sys.exit(1)

    if not database_url:
        print("✗ Error: DATABASE_URL must be set")
        print("  Check your .env file or environment variables")
        sys.exit(1)

    # Initialize counters
    processed = 0
    skipped = 0
    added = 0
    dry_run_candidates = []

    # Connect to Twitch API
    print("\nConnecting to Twitch API...")
    try:
        twitch = await Twitch(twitch_client_id, twitch_client_secret)
        await twitch.authenticate_app([])
        print("✓ Authenticated\n")
    except Exception as e:
        print(f"✗ Error connecting to Twitch API: {e}")
        sys.exit(1)

    # Connect to database (unless dry run)
    conn = None
    if not dry_run:
        print("Connecting to database...")
        try:
            conn = await asyncpg.connect(database_url)
            print("✓ Connected\n")
        except Exception as e:
            print(f"✗ Error connecting to database: {e}")
            await twitch.close()
            sys.exit(1)
    else:
        print("DRY RUN MODE - No database changes will be made\n")

    # Search for streams
    print(f"Searching for streams in category {game_id} with {min_viewers}-{max_viewers} viewers...")
    print(f"Target: {limit} new streamer(s)\n")

    try:
        # Get live streams for specified game
        streams = twitch.get_streams(
            game_id=game_id,
            first=100  # Max results per page
        )

        # Process streams with pagination
        async for stream in streams:
            processed += 1

            # Filter by viewer count
            if not (min_viewers <= stream.viewer_count <= max_viewers):
                continue

            # This stream matches our criteria
            streamer_id = int(stream.user_id)
            username = stream.user_login
            viewer_count = stream.viewer_count

            print(f"[{added + 1}/{limit}] Found: {username} ({viewer_count} viewers)")

            # Check if already exists (skip in dry-run)
            if not dry_run:
                exists = await check_streamer_exists(conn, streamer_id)

                if exists:
                    print(f"  ⊘ Already tracked, skipping\n")
                    skipped += 1
                    continue

            # Get full user profile
            print(f"  → Fetching user profile...")
            user_data = await get_twitch_user_data(twitch, stream.user_id)

            if not user_data:
                print(f"  ✗ Could not fetch user data, skipping\n")
                continue

            # In dry-run mode, just collect candidates
            if dry_run:
                dry_run_candidates.append({
                    'username': user_data['login'],
                    'display_name': user_data['display_name'],
                    'viewer_count': viewer_count
                })
                print(f"  ✓ Would add {user_data['login']} ({user_data['display_name']})\n")
                added += 1
            else:
                # Insert into database
                print(f"  → Adding to database...")
                try:
                    await insert_streamer(
                        conn,
                        user_data['id'],
                        user_data['login'],
                        user_data['display_name'],
                        user_data['profile_image_url'],
                        user_data['description'],
                        user_data['created_at']
                    )
                    print(f"  ✓ Added {user_data['login']} ({user_data['display_name']})\n")
                    added += 1
                except Exception as e:
                    print(f"  ✗ Error inserting streamer: {e}\n")
                    continue

            # Check if we've reached the limit
            if added >= limit:
                print(f"Reached limit of {limit} streamers, stopping search.\n")
                break

        # Print summary
        print("=" * 60)
        if dry_run:
            print("DRY RUN SUMMARY:")
            print("=" * 60)
            if dry_run_candidates:
                print("\nWould add the following streamers:")
                for i, candidate in enumerate(dry_run_candidates, 1):
                    print(f"  {i}. {candidate['username']} ({candidate['display_name']}) - {candidate['viewer_count']} viewers")
            else:
                print("\nNo new streamers found matching criteria")
        else:
            print("DISCOVERY SUMMARY:")
            print("=" * 60)
            print(f"  Streams processed: {processed}")
            print(f"  Already tracked: {skipped}")
            print(f"  Newly added: {added}")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error during stream search: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if conn:
            await conn.close()
        await twitch.close()

    return processed, skipped, added


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Discover and add new Twitch streamers to tracking database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discover small "Just Chatting" streamers
  python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 10

  # Discover mid-size "League of Legends" streamers
  python discover.py --game-id 21779 --min-viewers 100 --max-viewers 500 --limit 20

  # Test without making changes
  python discover.py --game-id 509658 --min-viewers 50 --max-viewers 250 --limit 5 --dry-run

Common Game IDs:
  - Just Chatting: 509658
  - League of Legends: 21779
  - Fortnite: 33214
  - Minecraft: 27471
  - Valorant: 516575
  - Grand Theft Auto V: 32982
        """
    )

    # Required arguments
    parser.add_argument(
        '--game-id',
        required=True,
        type=str,
        help='Twitch game/category ID (e.g., 509658 for "Just Chatting")'
    )

    parser.add_argument(
        '--min-viewers',
        required=True,
        type=int,
        help='Minimum concurrent viewers (e.g., 50)'
    )

    parser.add_argument(
        '--max-viewers',
        required=True,
        type=int,
        help='Maximum concurrent viewers (e.g., 250)'
    )

    # Optional arguments
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Maximum number of streamers to add (default: 10)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be added without making database changes'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.min_viewers < 0:
        print("✗ Error: --min-viewers must be non-negative")
        sys.exit(1)

    if args.max_viewers < args.min_viewers:
        print("✗ Error: --max-viewers must be >= --min-viewers")
        sys.exit(1)

    if args.limit <= 0:
        print("✗ Error: --limit must be positive")
        sys.exit(1)

    # Print configuration
    print("\n" + "=" * 60)
    print("TWITCH STREAMER DISCOVERY")
    print("=" * 60)
    print(f"Game ID: {args.game_id}")
    print(f"Viewer range: {args.min_viewers} - {args.max_viewers}")
    print(f"Target limit: {args.limit}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    # Run discovery
    try:
        asyncio.run(discover_streamers(
            game_id=args.game_id,
            min_viewers=args.min_viewers,
            max_viewers=args.max_viewers,
            limit=args.limit,
            dry_run=args.dry_run
        ))
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
