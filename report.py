from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from materials import Material

REPORTS_DIR = Path("reports")


# ---------------------------------------------------------------------------
# section renderers
# ---------------------------------------------------------------------------


def _fmt(val: Any, default: str = "—", unit: str = "") -> str:
    if val is None or (isinstance(val, float) and val == 0.0) or val == "":
        return default
    if isinstance(val, float):
        if abs(val) >= 1e8 and not unit:
            return f"{val / 1e8:.2f} 亿"
        if abs(val) >= 1e4 and not unit:
            return f"{val / 1e4:.2f} 万"
        return f"{val:.2f}"
    return str(val)


def _profile_section(profile) -> str:
    """Render company overview from CompanyProfile dataclass."""
    lines = ["## 一、公司概况", ""]

    # header
    lines.append(f"**{profile.name}**（{profile.ticker}）")
    if profile.name_en:
        lines.append(f"*{profile.name_en}*")
    lines.append("")

    # basic info table
    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 所属行业 | {profile.industry} |")
    lines.append(f"| 上市市场 | {profile.market} |")
    lines.append(f"| 成立日期 | {profile.established_date} |")
    lines.append(f"| 上市日期 | {profile.listing_date} |")
    lines.append(f"| 法人代表 | {profile.legal_rep} |")
    if profile.website:
        lines.append(f"| 官方网站 | {profile.website} |")
    lines.append("")

    # market data
    lines.append("| 市场数据 | |")
    lines.append("|----------|------|")
    lines.append(f"| 最新价 | {_fmt(profile.latest_price, '—')} 元 |")
    lines.append(f"| 涨跌幅 | {_fmt(round((profile.latest_price / profile.prev_close - 1) * 100, 2) if profile.prev_close > 0 else None, '—')}% |")
    if profile.total_shares:
        lines.append(f"| 总股本 | {_fmt(profile.total_shares, '—')} 亿股 |")
    if profile.market_cap:
        cap = profile.market_cap
        if cap >= 10000:
            lines.append(f"| 总市值 | {cap / 10000:.2f} 万亿元 |")
        else:
            lines.append(f"| 总市值 | {cap:.2f} 亿元 |")
    if profile.pe_ttm:
        lines.append(f"| PE (TTM) | {_fmt(profile.pe_ttm, '—')} 倍 |")
    lines.append(f"| 成交量 | {_fmt(profile.volume / 10000, '—')} 万手" if profile.volume else "| 成交量 | — |")
    lines.append(f"| 成交额 | {_fmt(profile.amount / 1e8, '—')} 亿元" if profile.amount else "| 成交额 | — |")
    lines.append(f"| 更新时间 | {profile.update_time} |")
    lines.append("")

    # business description
    if profile.main_business:
        lines.append("**主营业务**")
        lines.append("")
        lines.append(f"{profile.main_business}")
        lines.append("")

    if profile.business_scope:
        lines.append("**经营范围**")
        lines.append("")
        lines.append(f"{profile.business_scope}")
        lines.append("")

    # company history (abbreviated)
    if profile.company_history:
        history = profile.company_history
        if len(history) > 300:
            history = history[:300] + "……"
        lines.append("**历史沿革**")
        lines.append("")
        lines.append(f"{history}")
        lines.append("")

    # contact
    lines.append(f"**联系方式**：{profile.address}" +
                 (f" | {profile.email}" if profile.email else "") +
                 (f" | {profile.website}" if profile.website else ""))
    lines.append("")

    lines.append("> 数据来源：巨潮资讯网（公司概况）、新浪财经（实时行情）")
    return "\n".join(lines)


def _financials_section(financials: pd.DataFrame | None) -> str:
    if financials is None or financials.empty:
        return "## 二、财务表现\n\n*财务数据源不可用，暂缺*"
    lines = ["## 二、财务表现", ""]
    lines.append("| " + " | ".join(financials.columns) + " |")
    lines.append("|" + "|".join("---" for _ in financials.columns) + "|")
    for _, row in financials.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    lines.append("")
    lines.append("> 数据来源：同花顺（akshare `stock_financial_abstract_ths`），最近 6 个报告期")
    return "\n".join(lines)


def _sources_section(materials: list[Material]) -> str:
    lines = ["## 七、信息来源清单", ""]
    for m in materials:
        title = m.title or "(无标题)"
        lines.append(f"- [{m.n}] {title} — <{m.url}>")
    return "\n".join(lines)


def _disclaimer() -> str:
    return (
        "---\n\n"
        "**免责声明**：本报告由自动化流水线基于公开信息生成，"
        "仅用于技术学习与研究，不构成任何投资建议。"
    )


# ---------------------------------------------------------------------------
# render entry point
# ---------------------------------------------------------------------------


def render(
    ticker: str,
    profile,
    financials: pd.DataFrame | None,
    llm_sections: str,
    materials: list[Material],
) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    header = f"# 股票调研报告：{ticker}\n\n**数据截止日期**：{today}"
    body = "\n\n".join([
        header,
        _profile_section(profile),
        _financials_section(financials),
        llm_sections,
        _sources_section(materials),
        _disclaimer(),
    ])
    path = REPORTS_DIR / f"{ticker}_{today}.md"
    path.write_text(body + "\n", encoding="utf-8")
    return path
