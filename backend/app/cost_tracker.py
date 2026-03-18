"""
Per-request cost tracking for external API calls.

Tracks yfinance (free but rate-limited) and financialdatasets.ai (paid) calls.
Uses a ContextVar so each async request gets its own isolated counter.

Usage:
    # In middleware — initialize at request start:
    from app.cost_tracker import init_request_cost

    cost = init_request_cost()

    # In data service — increment as calls are made:
    from app.cost_tracker import get_request_cost

    get_request_cost().yf_calls += 1
    get_request_cost().fd_calls += 1

    # At request end (middleware logs automatically):
    cost.yf_calls, cost.fd_calls

Cost guard (prevent runaway paid API usage):
    from app.cost_tracker import get_request_cost, FD_CALL_LIMIT

    if get_request_cost().fd_calls >= FD_CALL_LIMIT:
        # skip paid API, fall back to cached/free data
        ...
"""
from contextvars import ContextVar
from dataclasses import dataclass, field

# Max paid API calls allowed per request before we fall back to cached/free data
FD_CALL_LIMIT = 10


@dataclass
class RequestCost:
    yf_calls: int = 0   # yfinance calls (free but rate-limited)
    fd_calls: int = 0   # financialdatasets.ai calls (paid ~$0.001-0.01 each)

    def as_dict(self) -> dict:
        return {"yf_calls": self.yf_calls, "fd_calls": self.fd_calls}

    @property
    def is_over_fd_limit(self) -> bool:
        return self.fd_calls >= FD_CALL_LIMIT


# One RequestCost instance per async request — no threading issues
_request_cost: ContextVar[RequestCost] = ContextVar(
    "request_cost", default=RequestCost()
)


def init_request_cost() -> RequestCost:
    """Call at the start of each request to get a fresh counter."""
    cost = RequestCost()
    _request_cost.set(cost)
    return cost


def get_request_cost() -> RequestCost:
    """Get the current request's cost tracker. Safe to call from anywhere."""
    return _request_cost.get()
