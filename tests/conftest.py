"""Pytest configuration and fixtures."""

from pathlib import Path

import dotenv

# Set a valid JWT so Hatchet client can initialize during test collection.
# Prefer existing env; otherwise use a placeholder with required claims.
test_env_fpath = Path(__file__).parent / ".env.test"
dotenv.load_dotenv(test_env_fpath)
