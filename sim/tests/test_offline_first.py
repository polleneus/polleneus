"""P6 — the in-repo offline-first guard (runs EVERY suite, not just CI).

polleneus is offline-first: the SIMULATOR must run/deliver with NO network at runtime. This test rebinds the
socket module's connection entry points (socket.socket / create_connection / getaddrinfo) to raise, then
exercises the core sim paths (a delivery run + a scenario sweep). If any of those paths reached for the
network it would raise and this test would fail. Scope: it is a regression GUARD over the common
socket-based network stack (in-process), NOT a proof — subprocess / C-level network are out of scope, and
the sim today has no network code at all (so this pins that). The CI 'offline-first' job is the whole-
fast-suite version via conftest + POLLENEUS_OFFLINE_CI."""
import socket

from soup_sim.config import Config
from soup_sim.scenario import run_one, sweep


def _tiny():
    return Config(n=8, width=40.0, height=40.0, radius=12.0, boundary="torus", mobility="rwp",
                  speed_min=1.0, speed_max=1.0, dt=0.5, ttl=20.0, buffer_cap=10**6, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=20.0,
                  drain=0.0, n_messages=4, seen_margin=10.0, master_seed=7)


def test_sim_runs_with_network_blocked(monkeypatch):
    def deny(*_a, **_k):
        raise AssertionError("sim attempted network access — polleneus must be offline-first")
    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    # core delivery path
    r = run_one(_tiny())
    assert r["delivery_ratio"] >= 0.0
    # a scenario sweep (engine + oracle) also needs no network
    rows = sweep(_tiny(), densities=[2.0, 4.0], reps=2)
    assert len(rows) == 2 and all("delivery_mean" in row for row in rows)
