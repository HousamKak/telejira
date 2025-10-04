#!/usr/bin/env python3
"""Script to add an admin user to the preauthorized users table."""

import asyncio
import sys
from services.database import DatabaseService
from models import UserRole


async def add_admin(username: str):
    """Add a user as admin to preauthorized users."""
    db = DatabaseService("bot_data.db")

    try:
        await db.initialize()
        await db.add_preauthorized_user(username, UserRole.ADMIN)
        print(f"Successfully added @{username} as admin")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python add_admin.py <username>")
        print("Example: python add_admin.py Housamkak")
        sys.exit(1)

    username = sys.argv[1].lstrip("@")
    asyncio.run(add_admin(username))
