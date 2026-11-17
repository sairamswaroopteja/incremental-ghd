"""Resource budgets for exponential searches.

Exhausting a budget raises BudgetExhausted. A search that was cut short may only ever
report SearchStatus.NOT_FOUND (IMPLEMENTATION_PLAN §A.1.4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ighd.common.errors import BudgetExhausted


@dataclass
class Budget:
    """Expansion and wall-clock limits. ``None`` means unlimited."""

    max_expansions: int | None = None
    time_limit_s: float | None = None
    expansions: int = field(default=0, init=False)
    _started: float | None = field(default=None, init=False, repr=False)

    def start(self) -> "Budget":
        """Start (or restart) the clock and reset the expansion counter."""
        self.expansions = 0
        self._started = time.perf_counter()
        return self

    @property
    def elapsed_s(self) -> float:
        return 0.0 if self._started is None else time.perf_counter() - self._started

    def charge(self, n: int = 1) -> None:
        """Account for ``n`` search expansions; raise BudgetExhausted if a limit is exceeded."""
        if self._started is None:
            self.start()
        self.expansions += n
        if self.max_expansions is not None and self.expansions > self.max_expansions:
            raise BudgetExhausted(f"expansion budget {self.max_expansions} exceeded")
        if self.time_limit_s is not None and self.elapsed_s > self.time_limit_s:
            raise BudgetExhausted(f"time budget {self.time_limit_s}s exceeded")

    @property
    def unlimited(self) -> bool:
        return self.max_expansions is None and self.time_limit_s is None
