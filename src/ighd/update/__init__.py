"""M12: GHDUpdate (Algorithm 5), update strategies and results (paper §3.2, §5)."""

from ighd.update.pipeline import ghd_update
from ighd.update.result import Strategy, UpdateResult, UpdateTrace

__all__ = ["Strategy", "UpdateResult", "UpdateTrace", "ghd_update"]
