#!/usr/bin/env python3
"""Validate required environment variables for each deployment environment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_ALWAYS = [
    "DATABASE_URL",
    "SESSION_SECRET",
    "ADMIN_API_KEY",
    "FIELD_ENCRYPTION_KEY",
    "ADMIN_TOTP_SECRET",
]

ENV_FILE = Path(__file__).resolve().parent.parent / ".env.example"


def load_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def validate(app_env: str = "development") -> list[str]:
    env = load_env_example()
    errors: list[str] = []
    for key in REQUIRED_ALWAYS:
        if key not in env:
            errors.append(f"Missing {key} in .env.example")
    if app_env == "production":
        if env.get("CORS_ALLOW_ORIGINS", "*").strip() == "*":
            errors.append("CORS_ALLOW_ORIGINS must not be '*' in production config template")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="development", choices=["development", "production"])
    args = parser.parse_args()
    errors = validate(args.env)
    if errors:
        print("Environment validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"Environment template validation passed ({args.env}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
