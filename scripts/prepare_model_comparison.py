"""Prepare time-ordered experiment inputs; this command does not fit a model."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["date", "region", "industry", "age"]
NUMERIC = ["weekday", "is_weekend", "month_number", "day_index"]
CATEGORICAL = ["industry", "age"]
SPLITS = {
    "validation": ("2025-07-01", "2025-08-31", "2025-09-01", "2025-09-30"),
    "holdout": ("2025-07-01", "2025-09-30", "2025-10-01", "2025-12-31"),
}


def validate_keys(df, name):
    if df[KEY].isna().any().any() or df.duplicated(KEY).any():
        raise ValueError(f"{name}: missing or duplicate daily keys")


def prepare_features(card):
    df = card.copy()
    df["date"] = pd.to_datetime(df.date, format="%Y-%m-%d", errors="raise")
    validate_keys(df, "card")
    if not df.date.between("2025-07-01", "2025-12-31").all():
        raise ValueError("Dates outside study period")
    if df.amount.isna().any() or not np.isfinite(df.amount).all() or (df.amount < 0).any():
        raise ValueError("Invalid target")
    df["weekday"] = df.date.dt.dayofweek
    df["is_weekend"] = df.weekday.ge(5).astype(int)
    df["month_number"] = df.date.dt.month
    df["day_index"] = (df.date - pd.Timestamp("2025-07-01")).dt.days
    return df[KEY + ["amount"] + NUMERIC].sort_values(KEY).reset_index(drop=True)


def split_frames(features, name):
    start, end, vstart, vend = SPLITS[name]
    train = features.loc[features.date.between(start, end)].copy()
    evaluate = features.loc[features.date.between(vstart, vend)].copy()
    if train.empty or evaluate.empty or train.date.max() >= evaluate.date.min():
        raise ValueError("Empty split or non-chronological split")
    known = set(map(tuple, train[["industry", "age"]].drop_duplicates().to_numpy()))
    evaluate["seen_group_in_train"] = [tuple(k) in known for k in evaluate[["industry", "age"]].to_numpy()]
    return train, evaluate


def make_ai_model():
    """Fit preprocessing only on the training partition; no random early-stop split."""
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
    return Pipeline([
        ("features", ColumnTransformer([
            ("categories", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
            ("calendar", "passthrough", NUMERIC),
        ])),
        ("model", HistGradientBoostingRegressor(
            loss="squared_error", learning_rate=.05, max_iter=100,
            max_leaf_nodes=15, l2_regularization=1., early_stopping=False, random_state=42)),
    ])


def paired_metrics(actual, baseline, ai):
    """Require exactly the same observed evaluation keys, never silently drop cases."""
    frames = []
    for frame, column, name in [(actual, "amount", "actual"), (baseline, "prediction", "baseline"), (ai, "prediction", "ai")]:
        f = frame.copy()
        f["date"] = pd.to_datetime(f.date, format="%Y-%m-%d", errors="raise")
        validate_keys(f, name)
        if f.empty or not np.isfinite(f[column]).all() or (f[column] < 0).any():
            raise ValueError(f"{name}: missing, negative or non-finite values")
        frames.append(f.set_index(KEY)[column].sort_index())
    y, b, a = frames
    if not y.index.equals(b.index) or not y.index.equals(a.index):
        raise ValueError("Evaluation keys differ; report missing predictions before comparison")
    rows = []
    for label, pred in [("shared_baseline", b), ("hist_gradient_boosting", a)]:
        error = y - pred
        rows.append({"model": label, "rows": len(y), "mae": float(error.abs().mean()),
                     "rmse": float(np.sqrt((error ** 2).mean())),
                     "wape": float(error.abs().sum() / y.abs().sum()) if y.abs().sum() else None})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--card", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    features = prepare_features(pd.read_csv(args.card))
    summaries = []
    for name in SPLITS:
        train, evaluate = split_frames(features, name)
        # Keep actual target/features local; these CSVs must not be committed.
        train.to_csv(args.output / f"{name}_train.csv", index=False, encoding="utf-8-sig")
        evaluate.to_csv(args.output / f"{name}_evaluation.csv", index=False, encoding="utf-8-sig")
        summaries.append({"split": name, "train_start": str(train.date.min().date()),
                          "train_end": str(train.date.max().date()), "evaluation_start": str(evaluate.date.min().date()),
                          "evaluation_end": str(evaluate.date.max().date()), "train_days": train.date.nunique(),
                          "evaluation_days": evaluate.date.nunique(), "train_rows": len(train),
                          "evaluation_rows": len(evaluate), "unseen_group_rows": int((~evaluate.seen_group_in_train).sum())})
    pd.DataFrame(summaries).to_csv(args.output / "split_summary.csv", index=False, encoding="utf-8-sig")
    plan = {"status": "prepared_not_fitted", "model": "HistGradientBoostingRegressor",
            "numeric_features": NUMERIC, "categorical_features": CATEGORICAL,
            "target": "amount (provided source unit)", "baseline_status": "not_received",
            "comparison_status": "waiting_for_shared_baseline_and_common_protocol",
            "calendar_status": "full_calendar_not_received; holiday feature not enabled",
            "test_policy": "fit/tune with validation; freeze settings before holdout",
            "purpose": "future-period predictive comparison; not causal heat-loss validation"}
    (args.output / "experiment_readiness.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    main()
