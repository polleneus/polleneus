"""The fixed-size unit that floods the soup. Engine/policies see only these fields."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Blob:
    id: int
    created_at: float
    ttl: float
    size: float
    hop_energy: int | None = None  # optional; default non-binding in v1

    @property
    def expires_at(self) -> float:
        return self.created_at + self.ttl
