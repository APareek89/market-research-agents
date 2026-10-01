"""Server-owned execution context, inherited by async tasks and to_thread."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
import uuid

@dataclass(frozen=True)
class Execution:
    owner_id: str
    run_id: str
    mode: str = "live"
    example_id: str | None = None

_current: ContextVar[Execution | None] = ContextVar("mra_execution", default=None)

def current_execution() -> Execution:
    value = _current.get()
    if value is None:
        raise RuntimeError("A verified execution context is required")
    return value

@contextmanager
def execution_scope(value: Execution):
    uuid.UUID(value.owner_id)
    uuid.UUID(value.run_id)
    if value.mode not in {"live", "cached", "mock", "proof"}:
        raise ValueError("Invalid execution mode")
    token = _current.set(value)
    try:
        yield value
    finally:
        _current.reset(token)

def require_live_tools() -> None:
    if current_execution().mode != "live" or os.getenv("MRA_MOCK_MODE") == "1":
        raise RuntimeError("Research network tools are disabled for this execution")
