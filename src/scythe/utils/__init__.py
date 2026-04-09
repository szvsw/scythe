"""Utilities for working with the EP Engine."""

import math


def log_interval(total: int, *, max_logs: int = 20, min_interval: int = 5) -> int:
    """Compute a periodic logging interval for a loop of *total* iterations.

    Guarantees at most *max_logs* log calls and never logs more frequently
    than every *min_interval* steps.
    """
    return max(min_interval, math.ceil(total / max_logs)) if total > max_logs else 1
