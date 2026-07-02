#!/usr/bin/env python3
"""Generate a new admin API key and print rotation instructions."""

from __future__ import annotations

import secrets
import sys


def main() -> int:
    new_key = secrets.token_urlsafe(48)
    print("Admin API key rotation")
    print("======================")
    print()
    print("1. Set the current key as previous (dual-key window):")
    print("   ADMIN_API_KEY_PREVIOUS=<current ADMIN_API_KEY>")
    print()
    print("2. Set the new key:")
    print(f"   ADMIN_API_KEY={new_key}")
    print()
    print("3. Restart backend:")
    print("   docker compose up -d --build backend")
    print()
    print("4. After all clients updated, clear ADMIN_API_KEY_PREVIOUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
