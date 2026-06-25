"""Message workload: M messages, uniform-random distinct src/dst pairs, injected as a
cohort. src/dst are returned alongside each blob so the metrics oracle can score them;
the blob the engine sees carries no addressing.
"""
from __future__ import annotations
from .blob import Blob


def make_cohort(cfg, inject_time: float, rng):
    out = []
    for m in range(cfg.n_messages):
        src, dst = (int(x) for x in rng.choice(cfg.n, size=2, replace=False))
        blob = Blob(id=m, created_at=inject_time, ttl=cfg.ttl, size=cfg.blob_size)
        out.append((blob, src, dst))
    return out
