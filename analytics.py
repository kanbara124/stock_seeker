"""
Quantitative analytics for stock research reports.

Computes financial trends, sentiment scores, and source diversity
metrics from the raw data collected by the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from materials import Material

# ---------------------------------------------------------------------------
# financial trend analysis
# ---------------------------------------------------------------------------


@dataclass
class FinancialTrends:
    revenue_cagr_3y: float | None = None       # %
    profit_cagr_3y: float | None = None         # %
    latest_growth_yoy: float | None = None      # %
    growth_volatility: float | None = None      # std dev of YoY growth
    margin_latest: float | None = None          # %
    margin_trend: str = ""                      # "改善"/"恶化"/"平稳"
    periods_covered: int = 0


def _parse_fin(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).replace("亿", "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _build_annual_totals(financials: pd.DataFrame) -> dict[int, dict[str, float]]:
    """Sum single-quarter financials into annual totals, keyed by year."""
    rev_col = "营业总收入"
    profit_col = "净利润"
    by_year: dict[int, dict[str, float]] = {}
    for _, row in financials.iterrows():
        period = str(row["报告期"])
        year = int(period[:4])
        if year not in by_year:
            by_year[year] = {"revenue": 0.0, "profit": 0.0, "quarters": 0}
        by_year[year]["revenue"] += _parse_fin(row.get(rev_col, 0))
        by_year[year]["profit"] += _parse_fin(row.get(profit_col, 0))
        by_year[year]["quarters"] += 1
    return by_year


def compute_financial_trends(financials: pd.DataFrame) -> FinancialTrends:
    """Analyze financial data table for trends."""
    t = FinancialTrends()

    if financials is None or financials.empty:
        return t

    rev_col = "营业总收入"
    profit_col = "净利润"
    growth_col = "营业总收入同比增长率"
    profit_growth_col = "净利润同比增长率"

    if rev_col not in financials.columns:
        return t

    t.periods_covered = len(financials)

    # latest period growth
    if growth_col in financials.columns:
        try:
            t.latest_growth_yoy = _parse_fin(
                financials.iloc[0][growth_col]
            )
        except (IndexError, KeyError):
            pass

    # 3-year CAGR from trailing 12-month sums
    annual_summary = _build_annual_totals(financials)
    years_sorted = sorted(annual_summary.keys(), reverse=True)
    if len(years_sorted) >= 4:
        latest_year = years_sorted[0]
        three_years_ago = years_sorted[3]
        rev_latest = annual_summary[latest_year]["revenue"]
        rev_old = annual_summary[three_years_ago]["revenue"]
        profit_latest = annual_summary[latest_year]["profit"]
        profit_old = annual_summary[three_years_ago]["profit"]
        if rev_old > 0:
            t.revenue_cagr_3y = round(((rev_latest / rev_old) ** (1 / 3) - 1) * 100, 1)
        if profit_old > 0:
            t.profit_cagr_3y = round(((profit_latest / profit_old) ** (1 / 3) - 1) * 100, 1)

    # growth volatility (from YoY growth column)
    if growth_col in financials.columns:
        growths = [_parse_fin(v) for v in financials[growth_col]]
        growths = [g for g in growths if g != 0.0]
        if len(growths) >= 3:
            mean_g = sum(growths) / len(growths)
            var_g = sum((g - mean_g) ** 2 for g in growths) / len(growths)
            t.growth_volatility = round(var_g ** 0.5, 1)

    # margin trend
    if rev_col in financials.columns and profit_col in financials.columns:
        margins = []
        for _, row in financials.iterrows():
            rev = _parse_fin(row[rev_col])
            profit = _parse_fin(row[profit_col])
            if rev > 0:
                margins.append(round(profit / rev * 100, 1))

        if margins:
            t.margin_latest = margins[0]
            if len(margins) >= 3:
                if margins[0] > margins[-1] * 1.02:
                    t.margin_trend = "改善"
                elif margins[0] < margins[-1] * 0.98:
                    t.margin_trend = "恶化"
                else:
                    t.margin_trend = "平稳"

    return t


# ---------------------------------------------------------------------------
# guba sentiment quantification
# ---------------------------------------------------------------------------

BULLISH_KEYWORDS = [
    "涨", "利好", "翻倍", "起飞", "爆发", "买入", "看好", "低估",
    "反转", "拐点", "突破", "主升", "翻番", "牛市", "抄底", "加仓",
    "增持", "强烈推荐", "价值", "修复", "提升",
]
BEARISH_KEYWORDS = [
    "跌", "利空", "腰斩", "崩盘", "暴跌", "卖出", "看空", "高估",
    "泡沫", "退市", "亏损", "踩雷", "套牢", "割肉", "减持", "跑路",
    "完蛋", "没救", "垃圾", "危险", "下滑", "下降",
]


@dataclass
class SentimentScore:
    total_posts: int = 0
    bullish_pct: float = 0.0
    bearish_pct: float = 0.0
    neutral_pct: float = 0.0
    engagement_weighted_bullish: float = 0.0   # 0-100
    hot_topics: list[str] = None

    def __post_init__(self):
        if self.hot_topics is None:
            self.hot_topics = []


def score_guba_sentiment(posts: list) -> SentimentScore:
    """Quantify sentiment from guba post titles using keyword analysis."""
    s = SentimentScore()
    if not posts:
        return s

    bull_count = bear_count = 0
    weighted_score = 0.0
    total_weight = 0.0
    topic_counter: dict[str, int] = {}

    for p in posts:
        title = (p.title if hasattr(p, "title") else
                 p.get("title", "") if isinstance(p, dict) else "")
        reads = (p.reads if hasattr(p, "reads") else
                 p.get("reads", 0) if isinstance(p, dict) else 0)
        comments = (p.comments if hasattr(p, "comments") else
                    p.get("comments", 0) if isinstance(p, dict) else 0)

        bull_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in title)
        bear_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in title)

        weight = max(reads + comments * 10, 1)
        total_weight += weight

        if bull_hits > bear_hits:
            bull_count += 1
            weighted_score += weight * 80
        elif bear_hits > bull_hits:
            bear_count += 1
            weighted_score += weight * 20
        else:
            weighted_score += weight * 50

        # crude topic extraction: look for 2-4 char key phrases
        for phrase in ["提价", "涨价", "业绩", "分红", "回购", "库存",
                       "经销商", "批价", "消费", "系列酒", "改革", "估值",
                       "暴跌", "利好", "风险", "机会", "行业", "管理层"]:
            if phrase in title:
                topic_counter[phrase] = topic_counter.get(phrase, 0) + 1

    total = bull_count + bear_count
    if total > 0:
        s.bullish_pct = round(bull_count / (total + (len(posts) - total) * 0.5) * 100, 1)
        s.bearish_pct = round(bear_count / (total + (len(posts) - total) * 0.5) * 100, 1)
        s.neutral_pct = round(100 - s.bullish_pct - s.bearish_pct, 1)

    if total_weight > 0:
        s.engagement_weighted_bullish = round(weighted_score / total_weight, 1)

    s.total_posts = len(posts)
    s.hot_topics = sorted(topic_counter, key=topic_counter.get, reverse=True)[:5]

    return s


# ---------------------------------------------------------------------------
# source diversity
# ---------------------------------------------------------------------------


@dataclass
class SourceDiversity:
    total: int = 0
    t1_count: int = 0       # 公告
    t3_count: int = 0       # 新闻
    t4_report_count: int = 0  # 研报
    t4_forum_count: int = 0   # 讨论/情绪
    total_chars: int = 0
    date_range: str = ""


def analyze_sources(materials: list[Material]) -> SourceDiversity:
    """Categorize materials by source tier and compute coverage stats."""
    d = SourceDiversity()
    if not materials:
        return d

    d.total = len(materials)
    dates: list[str] = []

    for m in materials:
        d.total_chars += len(m.text or "")
        url = m.url or ""

        if "cninfo.com.cn" in url:
            d.t1_count += 1
        elif any(d in url for d in ["eastmoney.com", "stcn.com", "21jingji.com",
                                      "caixin.com", "yicai.com", "jiemian.com",
                                      "wallstreetcn.com", "cls.cn", "thepaper.cn"]):
            d.t3_count += 1
        elif "nxny.com" in url:
            d.t4_report_count += 1
        elif "xueqiu.com" in url or "guba://" in url:
            d.t4_forum_count += 1

    return d


# ---------------------------------------------------------------------------
# causal chain analysis (LLM-powered, non-thinking)
# ---------------------------------------------------------------------------

_CAUSAL_PROMPT = """你是产业分析师。根据以下 {ticker} 的材料，提取并串联**产业因果传导链**。

要求：
1. 识别 3-5 条核心因果链，每条按 "上游力量 → 公司动作 → 下游结果" 格式输出。
2. 区分**行业驱动**（宏观/政策/技术 → 行业供需变化）和**公司响应**（战略/产品/渠道 → 财务表现）。
3. 标注每条因果链的证据来源编号 [n]。
4. 指出因果链中的**薄弱环节**：哪一步的假设最脆弱？若该假设不成立，整条链会如何崩塌？
5. 不要在因果链中做估值判断或投资建议。

输出格式（每条 80-150 字）：
### 因果链 N：概括性标题
- 行业驱动：…… [n]
- 公司响应：…… [n]
- 财务/市场结果：…… [n]
- 薄弱环节：……

材料：
{materials}
"""


def analyze_causal_chains(
    ticker: str, materials: list[Material],
) -> str:
    """Use LLM to extract industry→company→financial causal chains."""
    if not materials:
        return ""

    blocks = []
    for m in materials[:30]:  # limit to top 30 for cost
        text = (m.text or "")[:600]
        blocks.append(f"[{m.n}] {m.title}\n{text}")

    prompt = _CAUSAL_PROMPT.format(
        ticker=ticker,
        materials="\n\n".join(blocks),
    )

    import os
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return ""
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        timeout=120,
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# combined analytics report
# ---------------------------------------------------------------------------


def build_analytics_text(
    trends: FinancialTrends,
    sentiment: SentimentScore,
    sources: SourceDiversity,
    causal_chains: str = "",
    peer_comparison_text: str = "",
) -> str:
    """Generate a structured analytics summary for injection into the LLM prompt."""
    lines = ["---", "## 数据洞察（自动化分析）", ""]

    # financial
    lines.append("**财务趋势**")
    if trends.periods_covered:
        if trends.revenue_cagr_3y is not None:
            lines.append(f"- 近 3 年营收 CAGR：{trends.revenue_cagr_3y}%")
        if trends.profit_cagr_3y is not None:
            lines.append(f"- 近 3 年净利润 CAGR：{trends.profit_cagr_3y}%")
        if trends.latest_growth_yoy is not None:
            lines.append(f"- 最新报告期营收同比：{trends.latest_growth_yoy}%")
        if trends.growth_volatility is not None:
            lines.append(f"- 营收增速波动率（标准差）：{trends.growth_volatility}")
        if trends.margin_latest is not None:
            lines.append(f"- 最新净利率：{trends.margin_latest}%（趋势：{trends.margin_trend or '—'}）")
    else:
        lines.append("- 财务数据不可用")
    lines.append("")

    # sentiment
    lines.append("**股吧情绪量化**")
    if sentiment.total_posts:
        if sentiment.bullish_pct > 0:
            lines.append(f"- 情绪分布：看多 {sentiment.bullish_pct}% / 看空 {sentiment.bearish_pct}% / 中性 {sentiment.neutral_pct}%")
        lines.append(f"- 互动加权情绪分：{sentiment.engagement_weighted_bullish}/100 " +
                     ("（偏乐观）" if sentiment.engagement_weighted_bullish > 55 else
                      "（偏悲观）" if sentiment.engagement_weighted_bullish < 45 else "（中性）"))
        if sentiment.hot_topics:
            lines.append(f"- 高频话题：{'、'.join(sentiment.hot_topics)}")
    else:
        lines.append("- 股吧数据不可用")
    lines.append("")

    # sources
    lines.append("**来源覆盖统计**")
    lines.append(f"- 素材总数：{sources.total} 篇，总计约 {sources.total_chars:,} 字符")
    lines.append(f"- T1 公告：{sources.t1_count} 篇 | T3 新闻：{sources.t3_count} 篇")
    lines.append(f"- T4 研报：{sources.t4_report_count} 篇 | T4 讨论/情绪：{sources.t4_forum_count} 篇")
    lines.append("")

    if causal_chains:
        lines.append(causal_chains)
        lines.append("")

    if peer_comparison_text:
        lines.append(peer_comparison_text)
        lines.append("")

    lines.append("*以上数据由程序自动计算，供 LLM 在撰写报告时参考。*")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# peer comparison analytics
# ---------------------------------------------------------------------------


def build_peer_comparison_text(
    target_name: str,
    target_revenue: str,
    target_revenue_yoy: str,
    target_profit: str,
    target_profit_yoy: str,
    peers: list,   # list of PeerFinancialSnapshot
) -> str:
    """Generate a peer comparison table and summary for LLM consumption."""
    if not peers:
        return ""

    lines = ["**同业比较（自动化计算）**", ""]
    lines.append(f"目标公司：{target_name}")
    lines.append(f"  最新一期营收：{target_revenue}    营收同比：{target_revenue_yoy}")
    lines.append(f"  最新一期净利润：{target_profit}    净利润同比：{target_profit_yoy}")
    lines.append("")

    lines.append("| 公司 | 营收 | 营收同比 | 净利润 | 净利润同比 |")
    lines.append("|------|------|----------|--------|------------|")
    for p in peers:
        rev = p.revenue or "—"
        rev_yoy = p.revenue_yoy or "—"
        profit = p.profit or "—"
        profit_yoy = p.profit_yoy or "—"
        lines.append(f"| {p.name}({p.ticker}) | {rev} | {rev_yoy} | {profit} | {profit_yoy} |")

    lines.append("")
    lines.append("*同业财务数据来源于同花顺（akshare），仅展示最近一个报告期。*")
    return "\n".join(lines)
