"""Reproduce descriptive card/SKT comparisons without asserting a region mapping."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

MONTHS = [f"2025{m:02d}" for m in range(7, 13)]
AGES = ["10대", "20대", "30대", "40대", "50대", "60대 이상"]
SCOPES = ["all_observed", "common_6months"]
KEY = ["date", "region", "industry", "age"]


def unique(df, keys, name):
    if df[keys].isna().any().any() or df.duplicated(keys).any():
        raise ValueError(f"{name}: missing/duplicate keys {keys}")


def index_july(values):
    """Explicit reference month; never depend on incoming row order."""
    values = values.reindex(MONTHS)
    if values.isna().any() or values.loc["202507"] <= 0:
        raise ValueError("Six months and a positive July reference are required")
    return values / values.loc["202507"] * 100


def summarize(card, profiles, coverage, prefix="32010"):
    card = card.copy()
    card["date"] = pd.to_datetime(card.date, format="%Y-%m-%d", errors="raise")
    unique(card, KEY, "card")
    if set(card.region) != {"강원 춘천시"} or set(card.age) != set(AGES):
        raise ValueError("Expected Chuncheon personal-card data and six age groups")
    if not card.date.between("2025-07-01", "2025-12-31").all():
        raise ValueError("Card dates outside July–December 2025")
    if card.amount.isna().any() or (card.amount < 0).any():
        raise ValueError("Invalid card amount")
    card["month"] = card.date.dt.strftime("%Y%m")
    monthly = card.groupby(["month", "age"], as_index=False).agg(
        amount=("amount", "sum"), observed_days=("date", "nunique"))
    monthly["calendar_days"] = pd.to_datetime(monthly.month, format="%Y%m").dt.days_in_month
    # These checks concern date presence, not completeness of all merchants/strata.
    if len(monthly) != 36 or not monthly.observed_days.eq(monthly.calendar_days).all():
        raise ValueError("Card age/month date coverage differs; do not fill absence with zero")
    monthly["amount_per_calendar_day"] = monthly.amount / monthly.calendar_days
    monthly["card_share"] = monthly.amount / monthly.groupby("month").amount.transform("sum")
    p = profiles.loc[profiles.prefix.astype(str).eq(prefix)].copy()
    c = coverage.loc[coverage.prefix.astype(str).eq(prefix)].copy()
    unique(p, ["month", "type", "scope", "variable"], "SKT profiles")
    unique(c, ["month", "type"], "SKT coverage")
    if set(p.type) != {"age", "time", "wkdy"} or set(p.scope) != set(SCOPES):
        raise ValueError("Missing SKT type or grid scope")
    if p.grid_value_sum.isna().any() or (p.grid_value_sum < 0).any():
        raise ValueError("Invalid SKT measure")
    expected_variables = {"age": set(AGES), "time": {f"TMST_{h:02d}" for h in range(24)},
                          "wkdy": {f"FLOW_POP_CNT_{d}" for d in ["MON", "TUS", "WED", "THU", "FRI", "SAT", "SUN"]}}
    for kind, variables in expected_variables.items():
        for scope in SCOPES:
            part = p.loc[p.type.eq(kind) & p.scope.eq(scope)]
            if set(part.month) != set(MONTHS):
                raise ValueError("Missing SKT month")
            for _, group in part.groupby("month"):
                if set(group.variable) != variables or group.grid_value_sum.sum() <= 0:
                    raise ValueError("Incomplete SKT profile")
    expected_coverage = {(m, k) for m in MONTHS for k in expected_variables}
    if set(zip(c.month, c.type)) != expected_coverage:
        raise ValueError("Missing grid coverage records")
    if not ((c.common_grids > 0) & (c.common_grids <= c.observed_grids)).all():
        raise ValueError("Invalid common-grid coverage")
    if (c.groupby("type").common_grids.nunique() != 1).any():
        raise ValueError("Common-grid counts must be fixed across six months")
    grid_check = p.merge(c, on=["month", "type", "prefix"], validate="many_to_one")
    correct = np.where(grid_check.scope.eq("common_6months"), grid_check.common_grids, grid_check.observed_grids)
    if not np.array_equal(grid_check.grids.to_numpy(), correct):
        raise ValueError("Profile and coverage counts differ")
    p["profile_share"] = p.grid_value_sum / p.groupby(["month", "type", "scope"]).grid_value_sum.transform("sum")
    c["common_grid_fraction"] = c.common_grids / c.observed_grids
    totals = monthly.groupby("month").amount_per_calendar_day.sum().reindex(MONTHS).to_frame("card_daily_amount")
    totals["card_index"] = index_july(totals.card_daily_amount)
    flow = p.loc[p.type.eq("age")].groupby(["month", "scope"]).grid_value_sum.sum().unstack("scope")
    for scope in SCOPES:
        totals[f"skt_{scope}_index"] = index_july(flow[scope])
    age_flow = p.loc[p.type.eq("age")].rename(columns={"variable": "age"})
    comparison = monthly.merge(age_flow, on=["month", "age"], validate="one_to_many")
    for (_, _), idx in comparison.groupby(["age", "scope"]).groups.items():
        group = comparison.loc[idx].set_index("month")
        comparison.loc[idx, "card_index"] = comparison.loc[idx, "month"].map(index_july(group.amount_per_calendar_day))
        comparison.loc[idx, "skt_index"] = comparison.loc[idx, "month"].map(index_july(group.grid_value_sum))
    for df in [monthly, p, c, totals, comparison]:
        df["geography_status"] = "provisional"
    return monthly, p, c, totals, comparison


def plot_all(p, c, totals, comparison, out, font=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    if font:
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.unicode_minus": False, "figure.facecolor": "white", "savefig.dpi": 180})
    x = np.arange(6)
    labels = [f"{m}월" for m in range(7, 13)]
    colors = ["#176B87", "#C55A28", "#537A42", "#7556A5", "#B8860B", "#65717D"]
    subtitle = "SKT 32010 춘천 후보 · 지역코드 미확정 · 2025년 7–12월"
    foot = "출처: 제공 신한카드 데이터1·SKT 자료. 격자 합계는 고유 방문자 수가 아니며, 기후의 인과효과를 뜻하지 않음."
    files = []

    def save(fig, name, title, note):
        fig.suptitle(title, x=.06, y=.985, ha="left", fontsize=18, fontweight="bold")
        fig.text(.06, .934, subtitle, fontsize=10, color="#666666")
        fig.text(.06, .065, note, fontsize=9, color="#444444")
        fig.text(.06, .03, foot, fontsize=8, color="#666666")
        fig.tight_layout(rect=[.03, .12, .99, .9])
        fig.savefig(out / name)
        plt.close(fig)
        files.append(name)

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    for col, label, color, style in [
        ("card_index", "카드 매출 / 달력일 수", colors[0], "-"),
        ("skt_common_6months_index", "SKT 6개월 공통 격자", colors[1], "-"),
        ("skt_all_observed_index", "SKT 월별 전체 관측 격자", "#9A9A9A", "--")]:
        ax.plot(x, totals[col], marker="o", label=label, color=color, linestyle=style, linewidth=2)
    ax.axhline(100, color="#BBBBBB", linewidth=.8)
    ax.set(xticks=x, xticklabels=labels, ylabel="각 지표의 7월 = 100")
    ax.grid(axis="y", alpha=.2)
    ax.legend(loc="upper left", fontsize=10)
    save(fig, "01_monthly_trends.png", "월별 카드 매출과 유동인구 지표 비교",
         "카드: 춘천 개인카드·보고된 전체 업종. SKT: 연령표의 전 연령 합계. 각각 7월 대비 지수로 환산.")

    fig, axs = plt.subplots(2, 3, figsize=(12, 8.5), sharex=True)
    for ax, age in zip(axs.flat, AGES):
        z = comparison.loc[comparison.age.eq(age) & comparison.scope.eq("common_6months")].set_index("month").reindex(MONTHS)
        ax.plot(x, z.card_index, color=colors[0], marker="o", label="카드 달력일당 매출")
        ax.plot(x, z.skt_index, color=colors[1], marker="s", label="SKT 공통 격자")
        ax.set(title=age, xticks=x, xticklabels=labels, ylim=(75, 135))
        ax.axhline(100, color="#BBBBBB", linewidth=.7)
        ax.grid(axis="y", alpha=.2)
    axs[0, 0].legend(fontsize=8)
    # Use one shared range containing all observed indices, never clip values.
    vals = comparison.loc[comparison.scope.eq("common_6months"), ["card_index", "skt_index"]].to_numpy()
    low, high = np.floor(vals.min() / 10) * 10 - 5, np.ceil(vals.max() / 10) * 10 + 5
    for ax in axs.flat:
        ax.set_ylim(low, high)
    save(fig, "02_age_trends.png", "연령별 월별 흐름 비교 · 각 연령의 7월 = 100",
         "연령별 구성비나 소비 전환율이 아님. 카드 결제 고객과 SKT 관측 집단은 서로 연결된 개인 자료가 아님.")

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    for color, month in zip(colors, MONTHS):
        z = p.loc[p.type.eq("time") & p.scope.eq("common_6months") & p.month.eq(month)].sort_values("variable")
        ax.plot(np.arange(24), z.profile_share.to_numpy() * 100, label=f"{int(month[-2:])}월", color=color, linewidth=1.8)
    ax.set(xlabel="시간대", ylabel="24개 시간대 지표 합 대비 구성비 (%)", xticks=range(0, 24, 2))
    ax.legend(ncol=3)
    ax.grid(axis="y", alpha=.2)
    save(fig, "03_hourly_profiles.png", "월별 시간대 유동인구 특성 · 공통 격자",
         "월별 시간대 집계의 상대적 구성. 특정 폭염 날짜의 시간대 변화나 일별 방문 회복으로 해석하지 않음.")

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    variables = [f"FLOW_POP_CNT_{d}" for d in ["MON", "TUS", "WED", "THU", "FRI", "SAT", "SUN"]]
    for color, month in zip(colors, MONTHS):
        z = p.loc[p.type.eq("wkdy") & p.scope.eq("common_6months") & p.month.eq(month)].set_index("variable").reindex(variables)
        ax.plot(range(7), z.grid_value_sum / z.grid_value_sum.mean() * 100, marker="o", label=f"{int(month[-2:])}월", color=color)
    ax.axhline(100, color="#BBBBBB", linewidth=.8)
    ax.set(xticks=range(7), xticklabels=list("월화수목금토일"), ylabel="그 달의 7개 요일 지표 평균 = 100")
    ax.legend(ncol=3)
    ax.grid(axis="y", alpha=.2)
    save(fig, "04_weekday_profiles.png", "월별 요일 유동인구 특성 · 공통 격자",
         "요일별 평균 지표의 상대적 크기. 해당 월의 요일별 실제 방문 횟수나 방문 비중이 아님.")

    fig, axs = plt.subplots(1, 3, figsize=(12, 6.8), sharey=True)
    for ax, kind, label in zip(axs, ["age", "time", "wkdy"], ["연령표", "시간대표", "요일표"]):
        z = c.loc[c.type.eq(kind)].set_index("month").reindex(MONTHS)
        ax.plot(x, z.common_grid_fraction * 100, marker="o", color=colors[0])
        ax.set(title=f"{label} · 공통 {int(z.common_grids.iloc[0]):,}개", xticks=x, xticklabels=labels, ylim=(0, 100))
        ax.grid(axis="y", alpha=.2)
    axs[0].set_ylabel("전체 관측 격자 중 공통 격자 (%)")
    save(fig, "05_grid_coverage.png", "관측 범위 점검 · 6개월 공통 격자의 비율",
         "자료 종류별로 공통 격자를 따로 정의. 계속 관측된 격자가 지역 전체를 대표한다고 가정하지 않음.")

    fig, axs = plt.subplots(1, 2, figsize=(12, 6.8), sharey=True)
    z = comparison.loc[comparison.scope.eq("common_6months")]
    for ax, col, title in zip(axs, ["card_share", "profile_share"], ["카드 월 매출 구성비", "SKT 연령 지표 구성비"]):
        bottom = np.zeros(6)
        for color, age in zip(colors, AGES):
            y = z.loc[z.age.eq(age)].set_index("month").reindex(MONTHS)[col].to_numpy() * 100
            ax.bar(x, y, bottom=bottom, label=age, color=color, width=.7)
            bottom += y
        ax.set(title=title, xticks=x, xticklabels=labels, ylim=(0, 100))
    axs[0].set_ylabel("각 자료 안의 구성비 (%)")
    axs[1].legend(ncol=3, loc="upper center", bbox_to_anchor=(.5, -.1), fontsize=9)
    save(fig, "06_age_composition.png", "연령 구성의 차이 · 서로 다른 모집단의 보조 비교",
         "카드는 금액 구성비, SKT는 공통 격자 연령 지표 구성비. 고객 수·1인당 매출·구매 전환율로 비교하지 않음.")
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ["card", "profiles", "coverage", "output"]:
        ap.add_argument("--" + arg, type=Path, required=True)
    ap.add_argument("--prefix", default="32010", choices=["32010"])
    ap.add_argument("--font", type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    read = lambda p: pd.read_csv(p, dtype={"month": str, "prefix": str})
    results = summarize(read(args.card), read(args.profiles), read(args.coverage), args.prefix)
    names = ["card_monthly_age", "skt_profiles", "grid_coverage", "monthly_trends", "age_comparison"]
    for name, df in zip(names, results):
        df.to_csv(args.output / f"{name}_PROVISIONAL.csv", index=name == "monthly_trends", encoding="utf-8-sig")
    monthly, p, c, totals, comparison = results
    figures = plot_all(p, c, totals, comparison, args.output, args.font)
    audit = {"geography_status": "provisional", "prefix": args.prefix,
             "source_files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.card, args.profiles, args.coverage]},
             "monthly_card_rows": len(monthly), "profile_rows": len(p), "comparison_rows": len(comparison),
             "card_date_presence_complete": bool(monthly.observed_days.eq(monthly.calendar_days).all()),
             "shares_sum_to_one": bool(np.allclose(p.groupby(["month", "type", "scope"]).profile_share.sum(), 1)),
             "figures": figures}
    (args.output / "monthly_validation.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(totals.drop(columns="card_daily_amount").round(2).to_string())
    print(f"Saved {len(figures)} provisional figures")


if __name__ == "__main__":
    main()
