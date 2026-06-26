"""CSV + (optional) plot output. Every CSV row carries the full parameter manifest so a
result is independently reproducible from the file alone. Plotting is import-guarded so
the core needs no GUI deps.
"""
from __future__ import annotations
import csv
import io

METRIC_FIELDS = ["density", "n", "delivery_mean", "ci_lo", "ci_hi",
                 "empirical_mean_degree", "overhead_mean", "stationary_ok"]


def to_csv_string(rows, manifest) -> str:
    man_fields = list(manifest.keys())
    header = METRIC_FIELDS + [f"param_{k}" for k in man_fields]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(k) for k in METRIC_FIELDS] + [manifest[k] for k in man_fields])
    return buf.getvalue()


def write_csv(rows, manifest, path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(to_csv_string(rows, manifest))


AIRTIME_FIELDS = ["density", "circulated_per_min_mean", "ci_lo", "ci_hi", "utilization_mean",
                  "delivery_mean", "t50"]
BINDING_KEYS = ["contention_bound", "setup_starved", "quantization", "demand_satisfied"]


def airtime_to_csv_string(rows, manifest) -> str:
    man = list(manifest.keys())
    header = AIRTIME_FIELDS + [f"binding_{k}" for k in BINDING_KEYS] + [f"param_{k}" for k in man]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(k) for k in AIRTIME_FIELDS]
                   + [r.get("binding", {}).get(k) for k in BINDING_KEYS]
                   + [manifest[k] for k in man])
    return buf.getvalue()


ANON_FIELDS = ["f", "arm", "realized_coverage", "rank1_prob", "ci_lo", "ci_hi",
               "median_err_firsthear", "median_err_origin", "p90_err", "p95_err",
               "anon_set_upper_bound", "unconditional_rank1", "undetected_fraction", "beats_random"]


def anonymity_to_csv_string(rows, manifest, scope_tag) -> str:
    """Anonymity CSV. The scope tag travels as a leading comment AND a column on every row
    (a comment alone is dropped by dataframe readers — every number must stay tagged)."""
    man = list(manifest.keys())
    header = ANON_FIELDS + ["scope_tag"] + [f"param_{k}" for k in man]
    buf = io.StringIO()
    buf.write(f"# {scope_tag}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(k) for k in ANON_FIELDS] + [scope_tag] + [manifest[k] for k in man])
    return buf.getvalue()


DEFENSE_FIELDS = ["arm", "baseline_rank1", "defended_rank1", "timing_only_rank1", "intersection",
                  "credited", "label", "delivery", "t50", "relay_density"]


def anonymity_defense_to_csv_string(out, manifest) -> str:
    """One row per defense arm (mixing, gate). Both honesty tags travel as columns + comments
    (a comment alone is dropped by dataframe readers). timing_only_rank1 is the TTL=inf control
    rank-1 (credit requires the drop to persist there); delivery + t50 are the cost of the defense."""
    man = list(manifest.keys())
    header = DEFENSE_FIELDS + ["scope_tag", "defense_scope_tag"] + [f"param_{k}" for k in man]
    buf = io.StringIO()
    buf.write(f"# {out['scope_tag']}\n# {out['defense_scope_tag']}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for arm in ("mixing", "gate"):
        a = out[arm]
        v = a["verdict"]
        row = [arm, a["baseline_rank1"], a["defended_rank1"], a.get("timing_only_rank1", ""),
               a["intersection"], v["credited"], v["label"],
               a["cost"]["delivery"], a["cost"]["t50"], a.get("relay_density", "")]
        w.writerow(row + [out["scope_tag"], out["defense_scope_tag"]] + [manifest[k] for k in man])
    return buf.getvalue()


def anonymity_plot(out, path) -> bool:
    """rank-1 probability vs coverage f per placement arm; scope tag in the title."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    fig, ax = plt.subplots()
    for arm in ("uniform", "chokepoint"):
        pts = [(r["f"], r["rank1_prob"]) for r in out["rows"] if r["arm"] == arm]
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=f"{arm}")
    ax.axhline(0.5, ls="--", lw=0.8, color="grey", label="exposure threshold")
    ax.set_xlabel("adversary coverage f")
    ax.set_ylabel("rank-1 (exact-catch) probability — UPPER BOUND")
    ax.set_title("polleneus source-exposure  " + out["scope_tag"])
    ax.legend()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True


def airtime_plot(out, path) -> bool:
    """Circulated-blobs/min vs density with the alpha=0 and cap/ttl control overlays + knee marker."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    def xy(rows):
        return [r["density"] for r in rows], [r["circulated_per_min_mean"] for r in rows]
    fig, ax = plt.subplots()
    x, y = xy(out["rows"])
    ax.plot(x, y, marker="o", label="airtime model")
    ax.plot(*xy(out["alpha0_rows"]), marker="s", ls="--", label="alpha=0 control")
    ax.plot(*xy(out["capttl_rows"]), marker="^", ls=":", label="cap=inf/ttl=inf control")
    if out["knee"]["status"] == "knee":
        ax.axvline(out["knee"]["knee"], color="grey", lw=0.8, label="knee")
    ax.set_xlabel("mean degree (nodes per radio-disk)")
    ax.set_ylabel("circulated blobs / min (UPPER BOUND)")
    ax.set_title(f"polleneus airtime: {out['gate']['label']}")
    ax.legend()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True


def plot(rows, path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    x = [r["density"] for r in rows]
    y = [r["delivery_mean"] for r in rows]
    lo = [r["ci_lo"] for r in rows]
    hi = [r["ci_hi"] for r in rows]
    fig, ax = plt.subplots()
    ax.plot(x, y, marker="o", label="delivery")
    ax.fill_between(x, lo, hi, alpha=0.2, label="95% CI")
    ax.axhline(0.5, ls="--", lw=0.8, color="grey")
    ax.set_xlabel("mean degree (nodes per radio-disk)")
    ax.set_ylabel("delivery ratio (UPPER BOUND)")
    ax.set_title("polleneus soup: delivery vs density")
    ax.legend()
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True
