from datetime import date
from pathlib import Path

import pandas as pd

from materials import Material

REPORTS_DIR = Path("reports")


def _profile_section(profile: pd.DataFrame) -> str:
    lines = ["## 一、公司概况", ""]
    for _, row in profile.iterrows():
        lines.append(f"- **{row['item']}**：{row['value']}")
    lines.append("")
    lines.append("> 说明：本节采用新浪财经轻量报价接口，暂缺行业/总市值/上市时间等字段（东财 push2 抓取限流待 M5 处理）。")
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
    lines = ["## 六、信息来源清单", ""]
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


def render(
    ticker: str,
    profile: pd.DataFrame,
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
