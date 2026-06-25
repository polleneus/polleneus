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
