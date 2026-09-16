"""Dataset 1 diagnostic: measure why the customer-support CSV carries no operational signal.

Reproduces, from the raw file, every number quoted in the diagnostic document:
synthetic-text evidence (placeholder, first sentences, random resolutions),
the 27-hour timestamp window with ~49% "resolved before first response",
the naive channel x priority x type table the brief asks for, association
tests of satisfaction against every available variable, and a negative
control (the Dataset 2 classifier pipeline applied to description -> type,
expected at chance).

Outputs:
  artifacts/ds1_metrics.json
  artifacts/figures/ds1_time_window.png

Run from the prototype root:  uv run python scripts/diagnostico_ds1.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline

PROTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTO))

DATA = PROTO / "data" / "customer_support_tickets.csv"
ART = PROTO / "artifacts"
FIG = ART / "figures" / "ds1_time_window.png"
OUT = ART / "ds1_metrics.json"

SEED = 42
PLACEHOLDER = "{product_purchased}"
NAIVE_DIMENSIONS = ["Ticket Channel", "Ticket Priority", "Ticket Type"]
CATEGORICAL_TESTS = {
    "ticket_channel": "Ticket Channel",
    "ticket_priority": "Ticket Priority",
    "ticket_type": "Ticket Type",
    "customer_gender": "Customer Gender",
    "product_purchased": "Product Purchased",
    "ticket_subject": "Ticket Subject",
}
# Same vectorizer/classifier configuration as scripts/train.py (Dataset 2).
TFIDF_CONFIG = dict(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=300_000)
LOGREG_CONFIG = dict(C=5, max_iter=2000)
VERDICT = (
    "As diferenças entre canais, prioridades e tipos cabem no ruído; "
    "tempo de resolução não é mensurável neste arquivo."
)

# Project palette (plan: navy / gold / gray) + status red for the zero reference.
NAVY = "#001F35"
GOLD = "#B9915B"
GRAY = "#9CA3AF"
DANGER = "#B3261E"
INK = "#0b0b0b"
SURFACE = "#FFFFFF"

try:  # shared normalization (Task 2); falls back to raw text if not present yet
    from app.normalize import normalize as _normalize  # type: ignore

    TEXT_NORMALIZATION = "app.normalize"
except Exception:  # pragma: no cover - only before Task 2 lands
    _normalize = None
    TEXT_NORMALIZATION = "raw"


def r4(x: float) -> float:
    return round(float(x), 4)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df["frt"] = pd.to_datetime(df["First Response Time"])
    df["ttr"] = pd.to_datetime(df["Time to Resolution"])
    df["delta_hours"] = (df["ttr"] - df["frt"]).dt.total_seconds() / 3600.0
    return df


def synthetic_text_evidence(df: pd.DataFrame) -> dict:
    desc = df["Ticket Description"].fillna("")
    first_sentence = desc.str.split(r"[.\n]", n=1, regex=True).str[0].str.strip()
    counts = first_sentence.value_counts()
    resolution = df["Resolution"].dropna()
    return {
        "placeholder": PLACEHOLDER,
        "placeholder_share": r4(desc.str.contains(PLACEHOLDER, regex=False).mean()),
        "first_sentence_distinct": int(counts.size),
        "first_sentence_top": [
            {"sentence": s, "n": int(n)} for s, n in counts.head(3).items()
        ],
        "resolution_n": int(resolution.size),
        "resolution_unique": int(resolution.nunique()),
        "resolution_avg_words": r4(resolution.str.split().str.len().mean()),
        "example_com_share": r4(df["Customer Email"].str.endswith("@example.com").mean()),
    }


def time_evidence(df: pd.DataFrame) -> dict:
    stamps = pd.concat([df["frt"], df["ttr"]]).dropna()
    both = df["delta_hours"].dropna()
    return {
        "time_window": {
            "start": stamps.min().isoformat(sep=" "),
            "end": stamps.max().isoformat(sep=" "),
        },
        "time_window_hours": r4((stamps.max() - stamps.min()).total_seconds() / 3600.0),
        "n_with_both_timestamps": int(both.size),
        "share_negative_resolution": r4((both < 0).mean()),
        "naive_delta_hours": {
            "mean": r4(both.mean()),
            "std": r4(both.std()),
            "min": r4(both.min()),
            "max": r4(both.max()),
        },
        "status_counts": {k: int(v) for k, v in df["Ticket Status"].value_counts().sort_index().items()},
    }


def naive_table(df: pd.DataFrame) -> list[dict]:
    """The table the brief asks for, computed exactly the naive way (and therefore meaningless)."""
    closed = df[df["Ticket Status"] == "Closed"]
    rows = []
    for dim in NAIVE_DIMENSIONS:
        for value in sorted(df[dim].dropna().unique()):
            grp = closed[closed[dim] == value]
            rows.append(
                {
                    "dimension": dim,
                    "value": str(value),
                    "n": int((df[dim] == value).sum()),
                    "n_closed": int(len(grp)),
                    "csat_mean": r4(grp["Customer Satisfaction Rating"].mean()),
                    "naive_hours_mean": r4(grp["delta_hours"].mean()),
                }
            )
    return rows


def association_tests(df: pd.DataFrame) -> list[dict]:
    """Does satisfaction move with anything? Kruskal + chi-square per categorical, Spearman per numeric."""
    closed = df[df["Customer Satisfaction Rating"].notna()].copy()
    csat = closed["Customer Satisfaction Rating"]
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name, col in CATEGORICAL_TESTS.items():
            groups = [g["Customer Satisfaction Rating"].to_numpy() for _, g in closed.groupby(col)]
            kw = stats.kruskal(*groups)
            table = pd.crosstab(closed[col], csat)
            chi2 = stats.chi2_contingency(table)
            out.append({"variable": name, "test": "kruskal", "n_groups": len(groups),
                        "statistic": r4(kw.statistic), "p_value": r4(kw.pvalue)})
            out.append({"variable": name, "test": "chi2", "n_groups": len(groups),
                        "statistic": r4(chi2[0]), "p_value": r4(chi2[1])})
        age = stats.spearmanr(closed["Customer Age"], csat)
        out.append({"variable": "customer_age", "test": "spearman",
                    "statistic": r4(age.statistic), "p_value": r4(age.pvalue)})
        frt_hour = closed["frt"].dt.hour
        hour = stats.spearmanr(frt_hour, csat)
        out.append({"variable": "frt_hour", "test": "spearman",
                    "statistic": r4(hour.statistic), "p_value": r4(hour.pvalue)})
    return out


def negative_control(df: pd.DataFrame) -> dict:
    """Dataset 2 pipeline on description -> type. If the text carried signal, this would beat chance."""
    texts = df["Ticket Description"].fillna("").astype(str)
    if _normalize is not None:
        texts = texts.map(_normalize)
    y = df["Ticket Type"].to_numpy()
    pipe = Pipeline(
        [
            ("tfidf", TfidfVectorizer(dtype=np.float32, **TFIDF_CONFIG)),
            ("clf", LogisticRegression(**LOGREG_CONFIG)),
        ]
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    scores = cross_val_score(pipe, texts.to_numpy(), y, cv=cv, scoring="accuracy", n_jobs=1)
    counts = df["Ticket Type"].value_counts()
    return {
        "task": "Ticket Description -> Ticket Type",
        "accuracy": r4(scores.mean()),
        "accuracy_std": r4(scores.std()),
        "fold_accuracies": [r4(s) for s in scores],
        "majority_share": r4(counts.iloc[0] / len(df)),
        "majority_class": str(counts.index[0]),
        "n_classes": int(counts.size),
        "chance": r4(1.0 / counts.size),
        "config": {
            "cv": "StratifiedKFold(5, shuffle=True, random_state=42)",
            "tfidf": TFIDF_CONFIG,
            "logreg": LOGREG_CONFIG,
            "text_normalization": TEXT_NORMALIZATION,
        },
    }


def plot_time_window(df: pd.DataFrame, share_negative: float) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    delta = df["delta_hours"].dropna().to_numpy()
    lo, hi = np.floor(delta.min()), np.ceil(delta.max())
    bins = np.arange(lo, hi + 1, 1.0)

    def pct(x: float) -> str:  # pt-BR decimal comma
        return f"{x:.1%}".replace(".", ",")

    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    counts, _, _ = ax.hist(delta, bins=bins, color=NAVY, edgecolor=SURFACE, linewidth=0.8)
    ax.axvline(0, color=DANGER, linestyle="--", linewidth=1.6)

    # headroom so the two direct labels sit above every bar, never on top of one
    top = counts.max() * 1.32
    ax.set_ylim(0, top)
    ax.text(-0.8, top * 0.97, f"{pct(share_negative)} dos tickets fechados:\n\"resolvido\" antes da 1ª resposta",
            ha="right", va="top", color=DANGER, fontsize=9.5)
    ax.text(0.8, top * 0.97, f"{pct(1 - share_negative)} depois", ha="left", va="top",
            color=INK, fontsize=9.5)

    n = f"{delta.size:,}".replace(",", ".")
    ax.set_title("Dataset 1: \"tempo de resolução\" ingênuo", loc="left", fontsize=11.5, color=INK, pad=20)
    ax.text(0, 1.02, f"Time to Resolution − First Response Time · n = {n} tickets fechados · "
                     "todos os timestamps numa janela de 27 h",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=8.5, color=GRAY)
    ax.set_xlabel("horas (negativo = resolvido antes da primeira resposta)", color=INK)
    ax.set_ylabel("tickets fechados", color=INK)

    ax.grid(axis="y", color="#E5E7EB", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRAY)
    ax.tick_params(colors=INK, labelsize=8.5)

    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG, facecolor=SURFACE)
    plt.close(fig)


def main() -> dict:
    if not DATA.exists():
        sys.exit(f"missing {DATA} - run `make data` first")
    df = load()

    text = synthetic_text_evidence(df)
    time = time_evidence(df)
    table = naive_table(df)
    tests = association_tests(df)
    control = negative_control(df)
    plot_time_window(df, time["share_negative_resolution"])

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"file": DATA.name, "sha256": sha256(DATA)},
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1] - 3),  # minus the 3 helper columns added in load()
        "n_closed": int((df["Ticket Status"] == "Closed").sum()),
        **text,
        **time,
        "csat": {
            "n": int(df["Customer Satisfaction Rating"].notna().sum()),
            "mean": r4(df["Customer Satisfaction Rating"].mean()),
            "std": r4(df["Customer Satisfaction Rating"].std()),
            "only_in_status": sorted(df.loc[df["Customer Satisfaction Rating"].notna(), "Ticket Status"].unique()),
        },
        "naive_table": table,
        "association_tests": tests,
        "negative_control": control,
        "verdict": VERDICT,
        "figure": str(FIG.relative_to(PROTO)),
    }
    ART.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"rows={metrics['n_rows']} placeholder={metrics['placeholder_share']:.1%} "
          f"first_sentences={metrics['first_sentence_distinct']} "
          f"window={metrics['time_window_hours']:.1f}h negative={metrics['share_negative_resolution']:.1%}")
    p_min = min(t["p_value"] for t in tests if t["variable"] != "frt_hour")
    print(f"association tests: {len(tests)}; min p (excluding frt_hour) = {p_min:.3f}")
    print(f"negative control: acc={control['accuracy']:.3f} ± {control['accuracy_std']:.3f} "
          f"(majority {control['majority_share']:.3f}, chance {control['chance']:.3f}, "
          f"text={TEXT_NORMALIZATION})")
    print(f"wrote {OUT.relative_to(PROTO)} and {FIG.relative_to(PROTO)}")
    return metrics


if __name__ == "__main__":
    main()
