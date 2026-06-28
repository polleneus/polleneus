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


RECON_COMPARE_FIELDS = [
    "density", "n",
    "off_circ_mean", "off_ci_lo", "off_ci_hi", "off_served_mean", "off_charged_mean", "off_util_mean",
    "on_circ_mean", "on_ci_lo", "on_ci_hi", "on_served_mean", "on_charged_mean", "on_util_mean",
    "on_recon_capped_episodes", "haircut",
]


def recon_compare_to_csv_string(rows, manifest) -> str:
    """One row per density: recon OFF arm + recon ON arm side-by-side + the haircut ratio
    (circ_on_mean/circ_off_mean). Full param manifest travels per row (independently reproducible).
    The OFF arm is bit-identical to the plain airtime numbers; the ON arm carries the recon schedule
    in the manifest (param_recon_cell_bytes / param_recon_c0 / param_recon_k)."""
    man = list(manifest.keys())
    header = RECON_COMPARE_FIELDS + [f"param_{k}" for k in man]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        off, on = r["off"], r["on"]
        w.writerow([
            r["density"], r["n"],
            off["circ_mean"], off["circ_ci_lo"], off["circ_ci_hi"], off["served_mean"],
            off["charged_mean"], off["util_mean"],
            on["circ_mean"], on["circ_ci_lo"], on["circ_ci_hi"], on["served_mean"],
            on["charged_mean"], on["util_mean"],
            on["recon_capped_episodes"], r["haircut"],
        ] + [manifest[k] for k in man])
    return buf.getvalue()


RECON_BAND_FIELDS = ["cell_bytes", "k", "circ_on_mean", "haircut", "recon_capped_episodes"]


def recon_band_to_csv_string(out, manifest) -> str:
    """One row per (cell_bytes, k) cell of the 2-D sensitivity band at a single saturated density.
    A leading comment carries the density / n / OFF circ baseline; haircut = circ_on_mean/circ_off_mean
    per cell. Full param manifest per row (recon_c0 is fixed from the base cfg; cell_bytes/k vary)."""
    man = list(manifest.keys())
    header = RECON_BAND_FIELDS + [f"param_{k}" for k in man]
    buf = io.StringIO()
    buf.write(f"# recon sensitivity band @ density={out['density']} n={out['n']} "
              f"circ_off_mean={out['circ_off_mean']:.3f}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for c in out["cells"]:
        w.writerow([c[k] for k in RECON_BAND_FIELDS] + [manifest[k] for k in man])
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


INTERSECTION_FIELDS = ["k", "fused_rank1_borda", "ci_lo_borda", "ci_hi_borda", "fused_rank1_score_sum",
                       "decoy_rank1", "random_floor_fused", "delivery", "n_samples"]


def intersection_to_csv_string(out, manifest) -> str:
    """One row per K. Both fusion rules (borda headline + score_sum sensitivity), the decoy-centrality
    control, and the fused-random floor travel per row. `headline_credited`/`headline_label` are the
    TABLE-level verdict (the headline-K decision), repeated on every row — NOT per-row. The generic tag
    is the PER-MESSAGE estimator scope (it does not model intersection — the FUSION layer does, hence
    intersection_scope_tag); both travel as columns + comments (a comment alone is dropped by readers)."""
    man = list(manifest.keys())
    header = (INTERSECTION_FIELDS + ["headline_credited", "headline_label",
              "per_message_scope_tag", "intersection_scope_tag"] + [f"param_{k}" for k in man])
    buf = io.StringIO()
    buf.write(f"# per-message estimator scope: {out['scope_tag']}\n# fusion layer: {out['intersection_scope_tag']}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    v = out["verdict"]
    for r in out["rows"]:
        row = [r.get(k) for k in INTERSECTION_FIELDS] + [v["credited"], v["label"],
               out["scope_tag"], out["intersection_scope_tag"]] + [manifest[k] for k in man]
        w.writerow(row)
    return buf.getvalue()


CLUSTER_FIELDS = ["leak", "n", "delivery_mean", "ci_lo", "ci_hi", "giant_mean",
                  "intra_degree", "inter_degree", "realized_degree"]


def cluster_to_csv_string(out, manifest) -> str:
    """One row per inter-cluster leak. The mobility-regime tag travels as a leading comment AND a
    column on every row (a comment alone is dropped by dataframe readers)."""
    man = list(manifest.keys())
    header = CLUSTER_FIELDS + ["regime_tag"] + [f"param_{k}" for k in man]
    buf = io.StringIO()
    buf.write(f"# {out['regime_tag']}  degree={out['degree']} rwp_delivery={out['rwp_delivery']:.3f} "
              f"rwp_recovered={out['rwp_recovered']}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in out["rows"]:
        w.writerow([r.get(k) for k in CLUSTER_FIELDS] + [out["regime_tag"]] + [manifest[k] for k in man])
    return buf.getvalue()


TOKEN_FIELDS = ["density", "n", "mode", "holder", "gossip_delay", "token_spend_interval",
                "slots_per_token_mean", "ci_lo", "ci_hi", "D_mean", "residual_mean",
                "max_slots_per_phy_mean", "giant_mean", "broken_at_D"]


def token_to_csv_string(rows, manifest, scope_tag) -> str:
    """One row per density for ONE regime arm of the token rate-limit sweep. The scope/honesty tag
    travels as a leading comment AND a column on every row (a comment alone is dropped by dataframe
    readers — every slots/token number must stay tagged as a LOWER BOUND on the leak). gossip_delay AND
    token_spend_interval travel on EVERY row (a slots/token gossip number is meaningless without the
    race operating point). The full param manifest travels per row so a result is independently
    reproducible from the file alone."""
    man = list(manifest.keys())
    header = TOKEN_FIELDS + ["scope_tag"] + [f"param_{k}" for k in man]
    buf = io.StringIO()
    buf.write(f"# {scope_tag}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(k) for k in TOKEN_FIELDS] + [scope_tag] + [manifest[k] for k in man])
    return buf.getvalue()


TOKEN_RACE_FIELDS = ["gossip_delay", "token_spend_interval", "rate_ratio", "slots_per_token_mean",
                     "ci_lo", "ci_hi", "residual_mean", "amplification", "gossip_wins"]


def token_race_to_csv_string(out, manifest, scope_tag) -> str:
    """The §4 HEADLINE race curve: one row per (gossip_delay, token_spend_interval) point, slots/token
    spanning ~1 (gossip wins) to ~D (burst defeats gossip). A leading comment carries density / n /
    broken (= D) reference; the scope tag travels as a comment AND a column. gossip_delay and
    token_spend_interval are on every row (the number is meaningless without them)."""
    man = list(manifest.keys())
    header = TOKEN_RACE_FIELDS + ["broken_D", "scope_tag"] + [f"param_{k}" for k in man]
    buf = io.StringIO()
    buf.write(f"# token rate-limit RACE @ density={out['density']} n={out['n']} broken(=D)={out['broken']:.2f} "
              f"holder={out['holder']}\n# {scope_tag}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in out["rows"]:
        w.writerow([r.get(k) for k in TOKEN_RACE_FIELDS] + [out["broken"], scope_tag]
                   + [manifest[k] for k in man])
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
