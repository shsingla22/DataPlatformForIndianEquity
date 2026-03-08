"""Report generation for dividend screener results.

Produces both terminal-friendly text and structured data for Showboat.
Generates two separate lists: PSU (Public Sector) and Private Sector.
"""

import json
from typing import Dict, List

from dividend_screener.screener import CompanyMetrics


def format_table(ranked: List[CompanyMetrics], label: str = "") -> str:
    """Format ranked companies as an ASCII table for terminal output."""
    lines = []
    header = (
        f"{'#':>3s}  {'Symbol':12s} {'Name':30s} {'Type':7s} "
        f"{'MktCap':>10s} {'DivYld%':>7s} {'Payout%':>7s} "
        f"{'EG%':>6s} {'PE':>6s} {'D/E':>5s} {'Score':>6s}"
    )
    if label:
        lines.append(label)
        lines.append("=" * len(header))
    lines.append(header)
    lines.append("-" * len(header))

    for i, m in enumerate(ranked, 1):
        lines.append(
            f"{i:3d}  {m.nse_symbol:12s} {m.name[:30]:30s} {m.ownership_type:7s} "
            f"{m.market_cap:10,.0f} {m.dividend_yield_pct:7.2f} {m.dividend_payout_pct:7.1f} "
            f"{m.earnings_growth_pct:6.1f} {m.pe_ratio:6.1f} {m.debt_to_equity:5.2f} "
            f"{m.composite_score:6.1f}"
        )

    return "\n".join(lines)


def _split_by_ownership(metrics: List[CompanyMetrics]):
    """Split metrics into PSU and Private lists."""
    psu = [m for m in metrics if m.ownership_type == "PSU"]
    private = [m for m in metrics if m.ownership_type == "Private"]
    return psu, private


def format_summary(all_metrics: List[CompanyMetrics],
                   ranked: List[CompanyMetrics],
                   top_per_category: int = 20) -> str:
    """Generate a textual summary with separate PSU and Private lists."""
    lines = []
    lines.append("=" * 80)
    lines.append("DIVIDEND VALUE SCREENER – RESULTS SUMMARY")
    lines.append("=" * 80)
    lines.append("")

    psu_all, private_all = _split_by_ownership(all_metrics)
    lines.append(f"Companies analysed:        {len(all_metrics)}")
    lines.append(f"  Public Sector (PSU):     {len(psu_all)}")
    lines.append(f"  Private Sector:          {len(private_all)}")

    avg_dy = sum(m.dividend_yield_pct for m in all_metrics) / len(all_metrics)
    avg_pe = sum(m.pe_ratio for m in all_metrics) / len(all_metrics)
    lines.append(f"Average dividend yield:    {avg_dy:.2f}%")
    lines.append(f"Average P/E ratio:         {avg_pe:.1f}x")
    lines.append("")

    # ── PSU Top 20 ───────────────────────────────────────────────────
    psu_ranked = sorted(psu_all, key=lambda m: m.composite_score, reverse=True)[:top_per_category]
    lines.append("")
    lines.append(format_table(psu_ranked, f"TOP {len(psu_ranked)} PUBLIC SECTOR (PSU) COMPANIES"))
    lines.append("")

    # PSU average stats
    if psu_all:
        avg_dy_psu = sum(m.dividend_yield_pct for m in psu_all) / len(psu_all)
        avg_pe_psu = sum(m.pe_ratio for m in psu_all) / len(psu_all)
        lines.append(f"  PSU Average Div Yield: {avg_dy_psu:.2f}%  |  PSU Average PE: {avg_pe_psu:.1f}x")
    lines.append("")

    # ── Private Top 20 ───────────────────────────────────────────────
    private_ranked = sorted(private_all, key=lambda m: m.composite_score, reverse=True)[:top_per_category]
    lines.append("")
    lines.append(format_table(private_ranked, f"TOP {len(private_ranked)} PRIVATE SECTOR COMPANIES"))
    lines.append("")

    # Private average stats
    if private_all:
        avg_dy_priv = sum(m.dividend_yield_pct for m in private_all) / len(private_all)
        avg_pe_priv = sum(m.pe_ratio for m in private_all) / len(private_all)
        lines.append(f"  Private Average Div Yield: {avg_dy_priv:.2f}%  |  Private Average PE: {avg_pe_priv:.1f}x")
    lines.append("")

    # ── Comparison ───────────────────────────────────────────────────
    lines.append("")
    lines.append("PSU vs PRIVATE COMPARISON")
    lines.append("-" * 50)
    if psu_ranked and private_ranked:
        psu_avg_score = sum(m.composite_score for m in psu_ranked) / len(psu_ranked)
        priv_avg_score = sum(m.composite_score for m in private_ranked) / len(private_ranked)
        psu_avg_yield = sum(m.dividend_yield_pct for m in psu_ranked) / len(psu_ranked)
        priv_avg_yield = sum(m.dividend_yield_pct for m in private_ranked) / len(private_ranked)
        psu_avg_pe = sum(m.pe_ratio for m in psu_ranked) / len(psu_ranked)
        priv_avg_pe = sum(m.pe_ratio for m in private_ranked) / len(private_ranked)
        psu_avg_growth = sum(m.earnings_growth_pct for m in psu_ranked) / len(psu_ranked)
        priv_avg_growth = sum(m.earnings_growth_pct for m in private_ranked) / len(private_ranked)

        lines.append(f"  {'Metric':25s} {'PSU Top 20':>12s} {'Private Top 20':>15s}")
        lines.append(f"  {'-'*25} {'-'*12} {'-'*15}")
        lines.append(f"  {'Avg Composite Score':25s} {psu_avg_score:12.1f} {priv_avg_score:15.1f}")
        lines.append(f"  {'Avg Dividend Yield':25s} {psu_avg_yield:11.2f}% {priv_avg_yield:14.2f}%")
        lines.append(f"  {'Avg P/E Ratio':25s} {psu_avg_pe:11.1f}x {priv_avg_pe:14.1f}x")
        lines.append(f"  {'Avg Earnings Growth':25s} {psu_avg_growth:11.1f}% {priv_avg_growth:14.1f}%")

    lines.append("")

    # ── Score breakdown for top 5 overall ────────────────────────────
    lines.append("SCORE BREAKDOWN – TOP 5 OVERALL")
    lines.append("-" * 70)
    lines.append(
        f"{'Symbol':12s} {'Type':7s} {'DivYld':>7s} {'Payout':>7s} {'Growth':>7s} "
        f"{'Value':>7s} {'BalSht':>7s} {'TOTAL':>7s}"
    )
    overall_top5 = sorted(all_metrics, key=lambda m: m.composite_score, reverse=True)[:5]
    for m in overall_top5:
        lines.append(
            f"{m.nse_symbol:12s} {m.ownership_type:7s} {m.score_div_yield:7.1f} "
            f"{m.score_payout:7.1f} {m.score_earnings_growth:7.1f} "
            f"{m.score_valuation:7.1f} {m.score_balance_sheet:7.1f} "
            f"{m.composite_score:7.1f}"
        )

    return "\n".join(lines)


def to_json(ranked: List[CompanyMetrics],
            top_per_category: int = 20) -> str:
    """Serialize ranked companies to JSON with PSU/Private split."""
    psu = sorted(
        [m for m in ranked if m.ownership_type == "PSU"],
        key=lambda m: m.composite_score, reverse=True
    )[:top_per_category]
    private = sorted(
        [m for m in ranked if m.ownership_type == "Private"],
        key=lambda m: m.composite_score, reverse=True
    )[:top_per_category]

    def _to_record(m, rank):
        return {
            "rank": rank,
            "nse_symbol": m.nse_symbol,
            "name": m.name,
            "ownership_type": m.ownership_type,
            "market_cap_crores": round(m.market_cap),
            "dividend_yield_pct": round(m.dividend_yield_pct, 2),
            "dividend_payout_pct": round(m.dividend_payout_pct, 1),
            "earnings_growth_pct": round(m.earnings_growth_pct, 1),
            "pe_ratio": round(m.pe_ratio, 1),
            "debt_to_equity": round(m.debt_to_equity, 2),
            "roe_pct": round(m.roe_pct, 1),
            "composite_score": round(m.composite_score, 1),
            "scores": {
                "dividend_yield": round(m.score_div_yield, 1),
                "payout_ratio": round(m.score_payout, 1),
                "earnings_growth": round(m.score_earnings_growth, 1),
                "valuation": round(m.score_valuation, 1),
                "balance_sheet": round(m.score_balance_sheet, 1),
            },
        }

    result = {
        "psu_top_20": [_to_record(m, i+1) for i, m in enumerate(psu)],
        "private_top_20": [_to_record(m, i+1) for i, m in enumerate(private)],
    }
    return json.dumps(result, indent=2)
