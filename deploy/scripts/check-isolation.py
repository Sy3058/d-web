#!/usr/bin/env python3
"""Check rendered private Compose configs without displaying values or retaining them."""

import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

AUTH_KEYS = ("JWT_SECRET", "PASSWORD_PEPPER", "TOKEN_PEPPER", "TOTP_ENCRYPTION_KEY")


def environment(config):
    values = config["services"]["api"]["environment"]
    if not isinstance(values, dict):
        raise ValueError("missing API environment")
    return {str(key).upper(): value for key, value in values.items()}


def storage_buckets(values):
    # Match Settings defaults when credentials enable R2 but bucket names are omitted.
    configured = any(
        values.get(key) for key in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
    )
    defaults = (
        {"R2_BUCKET": "dweb", "R2_PUBLIC_BUCKET": "dweb-cover"} if configured else {}
    )
    return {
        values.get(key, defaults.get(key)) for key in ("R2_BUCKET", "R2_PUBLIC_BUCKET")
    } - {None, ""}


def check_isolation(deployment_environment, current, other=None):
    if deployment_environment not in ("staging", "production"):
        raise ValueError("unsupported deployment environment")
    current = environment(current)
    if any(not current.get(key) for key in AUTH_KEYS):
        raise ValueError("API authentication secrets are incomplete")
    if other is None:
        if deployment_environment == "production":
            raise ValueError("staging config is required before production bootstrap")
        return
    other = environment(other)
    if any(not other.get(key) for key in AUTH_KEYS):
        raise ValueError("other environment authentication secrets are incomplete")
    if {current[key] for key in AUTH_KEYS} & {other[key] for key in AUTH_KEYS}:
        raise ValueError("staging and production authentication secrets must differ")
    first_password = urlsplit(current.get("DATABASE_URL", "")).password
    other_password = urlsplit(other.get("DATABASE_URL", "")).password
    if not first_password or not other_password or first_password == other_password:
        raise ValueError("staging and production DB credentials must differ")
    first_buckets = storage_buckets(current)
    other_buckets = storage_buckets(other)
    if first_buckets & other_buckets:
        raise ValueError("staging and production R2 buckets must differ")
    for key in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        if current.get(key) and current[key] == other.get(key):
            raise ValueError("staging and production R2 credentials must differ")


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: check-isolation.py ENV CURRENT_JSON [OTHER_JSON]")
    try:
        current = json.loads(Path(sys.argv[2]).read_text())
        other = (
            json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv) == 4 else None
        )
        check_isolation(sys.argv[1], current, other)
    except (ValueError, KeyError, TypeError, OSError):
        # Configs contain credentials: never print parser exceptions or source data.
        raise SystemExit(
            "Environment isolation check failed. Check separate credentials and R2 settings."
        )


if __name__ == "__main__":
    main()
