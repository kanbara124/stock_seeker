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
    lines.append("> 数据来源：同花顺（akshare `stock_financial_abstract_ths`，按单季度），最近 8 个报告期")
    return "\n".join(lines)


def _sources_section(materials: list[Material]) -> str:
    lines = ["## 十、信息来源清单", ""]
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
    path = REPORTS_DIR / f"{ticker}_{profile.name}_{today}.md"
    path.write_text(body + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

_PDF_CSS = """
@page {
    size: A4;
    margin: 2cm 2.2cm;
    @top-center {
        content: element(pageHeader);
    }
    @bottom-center {
        content: counter(page);
        font-size: 9pt;
        color: #888;
    }
}
body {
    font-family: "Microsoft YaHei", "SimHei", "Noto Sans SC", "PingFang SC", sans-serif;
    font-size: 11pt;
    line-height: 1.75;
    color: #222;
}
h1 { font-size: 18pt; border-bottom: 2px solid #1a3a5c; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 14pt; margin-top: 24px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
h3 { font-size: 12pt; margin-top: 18px; }
strong { color: #111; }
em { color: #555; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }
th, td { border: 1px solid #bbb; padding: 5px 8px; text-align: left; }
th { background: #eef3f8; font-weight: 600; }
blockquote { border-left: 3px solid #1a3a5c; padding-left: 12px; color: #555; margin: 8px 0; }
a { color: #1a3a5c; text-decoration: none; }
code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; font-size: 10pt; }
hr { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
pre { background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 10pt; }
div#pageHeader { font-size: 9pt; color: #999; text-align: right; padding-bottom: 4px; border-bottom: 1px solid #ddd; }
"""


def render_pdf(md_path: str | Path) -> Path | None:
    """Convert a markdown report to a styled PDF using weasyprint."""
    md_path = Path(md_path)
    if not md_path.exists():
        return None

    try:
        import markdown
        from weasyprint import HTML
    except ImportError:
        return None

    md_text = md_path.read_text(encoding="utf-8")

    md_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "nl2br"],
    )

    # Extract header for page header element
    first_h1_end = md_body.find("</h1>")
    page_header = ""
    if first_h1_end > 0:
        h1_content = md_body[:first_h1_end]
        h1_content = h1_content.replace("<h1>", "").replace("</h1>", "").replace("# ", "")
        page_header = h1_content.strip()

    pdf_path = md_path.with_suffix(".pdf")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>{_PDF_CSS}</style>
</head>
<body>
<div id="pageHeader">{page_header}</div>
{md_body}
</body>
</html>"""

    HTML(string=html).write_pdf(str(pdf_path))
    return pdf_path
