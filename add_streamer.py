#!/usr/bin/env python3
"""
Twitch Streamer Add Utility

A simple command-line tool to add known streamers by username to the tracking database.

Usage:
    python add_streamer.py --usernames shroud ninja
    python add_streamer.py --usernames xqc
    python add_streamer.py --dry-run --usernames test_user

This script:
1. Accepts one or more Twitch usernames
2. Fetches their full profiles from the Twitch API
3. Adds them to the streamers table (with duplicate protection)
4. Sets is_active = true so the ingestion service automatically tracks them

Requirements:
    - TWITCH_CLIENT_ID environment variable
    - TWITCH_CLIENT_SECRET environment variable
    - DATABASE_URL environment variable
"""

import asyncio
import argparse
import os
import sys
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import asyncpg
from twitchAPI.twitch import Twitch
from dotenv import load_dotenv


# ============================================================================
# Database Operations
# ============================================================================

async def insert_streamer(
    conn: asyncpg.Connection,
    user_data: Dict
) -> bool:
    """
    Insert streamer into database with duplicate protection.

    Uses ON CONFLICT DO NOTHING to make this operation idempotent.
    If the streamer already exists (by streamer_id), the insert is silently skipped.

    Args:
        conn: asyncpg database connection
        user_data: Dictionary with user data from Twitch API

    Returns:
        True if streamer was inserted, False if already existed (conflict)

    Note:
        This is superior to SELECT-then-INSERT because:
        - Single atomic operation (no race conditions)
        - Idempotent (safe to run multiple times)
        - Handles concurrent processes automatically
    """
    # Execute INSERT with ON CONFLICT
    result = await conn.execute(
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
        user_data['id'],
        user_data['login'],
        user_data['display_name'],
        user_data['profile_image_url'] if user_data['profile_image_url'] else None,
        user_data['description'] if user_data['description'] else None,
        user_data['created_at']
    )

    # Check if row was inserted (result will be "INSERT 0 1" for success, "INSERT 0 0" for conflict)
    # The format is "INSERT oid count" where count is number of rows inserted
    inserted = result.endswith(' 1')
    return inserted


# ============================================================================
# Twitch API Operations
# ============================================================================

async def fetch_users_from_twitch(
    twitch: Twitch,
    usernames: List[str]
) -> Tuple[List[Dict], List[str]]:
    """
    Fetch user data for multiple usernames from Twitch API.

    Args:
        twitch: Authenticated Twitch API client
        usernames: List of Twitch usernames (lowercase)

    Returns:
        Tuple of (found_users, not_found_usernames)
        - found_users: List of user data dicts
        - not_found_usernames: List of usernames that don't exist
    """
    found_users = []
    requested_usernames = [u.lower() for u in usernames]

    try:
        # Fetch all users in a single API call
        users_generator = twitch.get_users(logins=usernames)

        # Collect results
        async for user in users_generator:
            user_data = {
                'id': int(user.id),  # Convert string to int for database
                'login': user.login,
                'display_name': user.display_name,
                'profile_image_url': user.profile_image_url,
                'description': user.description,
                'created_at': user.created_at
            }
            found_users.append(user_data)

        # Determine which usernames were not found
        found_logins = {user['login'].lower() for user in found_users}
        not_found = [u for u in requested_usernames if u not in found_logins]

        return found_users, not_found

    except Exception as e:
        print(f"✗ Error fetching users from Twitch API: {e}")
        raise


# ============================================================================
# Main Logic
# ============================================================================

async def add_streamers(
    usernames: List[str],
    dry_run: bool = False
) -> None:
    """
    Add streamers to database by username.

    Args:
        usernames: List of Twitch usernames
        dry_run: If True, preview without making database changes
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

    if not database_url and not dry_run:
        print("✗ Error: DATABASE_URL must be set")
        print("  Check your .env file or environment variables")
        sys.exit(1)

    # Initialize counters
    total = len(usernames)
    added = 0
    skipped = 0
    failed = 0

    print(f"\nConnecting to Twitch API...")
    try:
        twitch = await Twitch(twitch_client_id, twitch_client_secret)
        await twitch.authenticate_app([])
        print("✓ Authenticated\n")
    except Exception as e:
        print(f"✗ Error connecting to Twitch API: {e}")
        sys.exit(1)

    # Fetch user data
    print(f"Fetching user data for: {', '.join(usernames)}\n")
    try:
        found_users, not_found = await fetch_users_from_twitch(twitch, usernames)
    except Exception as e:
        await twitch.close()
        sys.exit(1)

    # Report not found users
    if not_found:
        for username in not_found:
            print(f"✗ User not found: {username}")
            failed += 1
        print()

    # If no users found, exit early
    if not found_users:
        print("No valid users to process.\n")
        await twitch.close()
        sys.exit(0)

    # Dry run mode - just preview
    if dry_run:
        print("DRY RUN MODE - No database changes will be made\n")
        print("Would add the following streamers:")
        for user in found_users:
            print(f"  • {user['display_name']} (@{user['login']}) - ID: {user['id']}")
            print(f"    Created: {user['created_at']}")
            print(f"    Description: {user['description'][:60] if user['description'] else 'N/A'}...")
            print()
        print("=" * 60)
        print(f"Total users found: {len(found_users)}")
        print("=" * 60)
        await twitch.close()
        return

    # Connect to database
    print("Connecting to database...")
    try:
        conn = await asyncpg.connect(database_url)
        print("✓ Connected\n")
    except Exception as e:
        print(f"✗ Error connecting to database: {e}")
        await twitch.close()
        sys.exit(1)

    # Process each user
    print("Processing streamers...")
    for user in found_users:
        try:
            was_inserted = await insert_streamer(conn, user)

            if was_inserted:
                print(f"  ✓ Added: {user['display_name']} (@{user['login']}) - ID: {user['id']}")
                added += 1
            else:
                print(f"  - Skipped: {user['display_name']} (@{user['login']}) - ID: {user['id']} - already in database")
                skipped += 1

        except Exception as e:
            print(f"  ✗ Failed to add {user['login']}: {e}")
            failed += 1

    # Close connections
    await conn.close()
    await twitch.close()

    # Print summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total:   {total}")
    print(f"  Added:   {added}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed:  {failed}")
    print("=" * 60)

    if added > 0:
        print(f"\n✓ {added} streamer(s) added successfully.")
        print("  The ingestion service will automatically start tracking them.")


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """Parse arguments and run the add streamers process."""
    parser = argparse.ArgumentParser(
        description="Add Twitch streamers to tracking database by username",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --usernames shroud                    # Add single streamer
  %(prog)s --usernames shroud ninja pokimane     # Add multiple streamers
  %(prog)s --dry-run --usernames xqc             # Preview without adding

Notes:
  - Usernames are case-insensitive
  - Duplicate streamers are automatically skipped (idempotent)
  - Invalid usernames are reported but don't stop processing
  - Added streamers are automatically tracked by the ingestion service

Environment Variables:
  TWITCH_CLIENT_ID      - Twitch API client ID (required)
  TWITCH_CLIENT_SECRET  - Twitch API client secret (required)
  DATABASE_URL          - PostgreSQL connection string (required)
        """
    )

    parser.add_argument(
        '--usernames',
        nargs='+',
        required=True,
        help='One or more Twitch usernames to add'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview users without adding to database'
    )

    args = parser.parse_args()

    # Run async main
    try:
        asyncio.run(add_streamers(args.usernames, args.dry_run))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
