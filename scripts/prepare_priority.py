"""Define a pending priority-table template and safely join received event metrics."""
import argparse
from pathlib import Path

import pandas as pd

KEY = ["event_id", "region", "industry", "age", "window_start", "window_end"]
SALES = ["decline_rate", "gross_shortfall", "net_shortfall", "net_shortfall_rate", "sales_uncertainty_note"]
RECOVERY = ["recovery_days", "recovery_status", "recovery_uncertainty_note"]
DECISION = ["decline_only_rank", "support_priority", "priority_uncertainty_note", "review_status"]


def join_metrics(sales, recovery):
    """One event/window/granularity per row; no scoring rule is assumed."""
    for df, measures, label in [(sales, SALES, "sales"), (recovery, RECOVERY, "recovery")]:
        missing = set(KEY + measures) - set(df)
        if missing:
            raise ValueError(f"{label}: missing columns {sorted(missing)}")
        if df[KEY].isna().any().any() or df[KEY].astype(str).eq("").any().any() or df.duplicated(KEY).any():
            raise ValueError(f"{label}: missing/duplicate keys")
        start = pd.to_datetime(df.window_start, format="%Y-%m-%d", errors="raise")
        end = pd.to_datetime(df.window_end, format="%Y-%m-%d", errors="raise")
        if start.isna().any() or end.isna().any():
            raise ValueError(f"{label}: missing observation dates")
        if (start > end).any():
            raise ValueError("Invalid event observation window")
    if set(sales.columns) & set(recovery.columns) != set(KEY):
        raise ValueError("Ambiguous non-key columns")
    out = sales.merge(recovery, on=KEY, how="outer", validate="one_to_one", indicator=True)
    if not out._merge.eq("both").all():
        raise ValueError("Sales/recovery event-window keys differ")
    out = out.drop(columns="_merge")
    for col in DECISION:
        out[col] = pd.NA
    out["review_status"] = "pending_joint_rule_and_quality_review"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--sales", type=Path)
    ap.add_argument("--recovery", type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.sales is None) != (args.recovery is None):
        ap.error("Provide both --sales and --recovery, or neither to create empty templates")
    if args.sales is None:
        for name, fields in [("expected_event_sales", KEY + SALES), ("expected_recovery", KEY + RECOVERY),
                             ("support_priority_DRAFT", KEY + SALES + RECOVERY + DECISION)]:
            pd.DataFrame(columns=fields).to_csv(args.output / f"{name}.csv", index=False, encoding="utf-8-sig")
        print("Empty templates created: metrics not received, no rankings calculated")
    else:
        out = join_metrics(pd.read_csv(args.sales, dtype={k: str for k in KEY}),
                           pd.read_csv(args.recovery, dtype={k: str for k in KEY}))
        out.to_csv(args.output / "support_priority_DRAFT.csv", index=False, encoding="utf-8-sig")
        print(f"Joined {len(out)} rows; joint ranking rule still pending")


if __name__ == "__main__":
    main()
