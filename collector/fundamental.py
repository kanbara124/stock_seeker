from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import akshare as ak
import pandas as pd

from collector.rate_limit import safe_get

# ---------------------------------------------------------------------------
# Sina real-time quote
# ---------------------------------------------------------------------------

_SINA_FIELDS = [
    "股票简称", "今开", "昨收", "最新价", "今日最高", "今日最低",
    "竞买价", "竞卖价", "成交量(股)", "成交额(元)",
]


def _fetch_sina_quote(ticker: str) -> dict[str, str]:
    prefix = "sh" if ticker.startswith("6") else "sz"
    r = safe_get(
        f"https://hq.sinajs.cn/list={prefix}{ticker}",
        headers={"Referer": "https://finance.sina.com.cn"},
    )
    r.encoding = "gbk"
    payload = r.text.split('"', 2)[1]
    values = payload.split(",")
    data: dict[str, str] = {
        k: v for k, v in zip(_SINA_FIELDS, values[: len(_SINA_FIELDS)])
    }
    data["更新时间"] = f"{values[30]} {values[31]}"
    return data


# ---------------------------------------------------------------------------
# cninfo company profile
# ---------------------------------------------------------------------------

@dataclass
class CompanyProfile:
    ticker: str
    name: str
    name_en: str
    industry: str
    market: str
    listing_date: str
    established_date: str
    legal_rep: str
    registered_capital: str          # 万元
    main_business: str
    business_scope: str
    company_history: str
    website: str
    email: str
    address: str
    office: str
    # sino quote
    latest_price: float
    open: float
    prev_close: float
    high: float
    low: float
    volume: float
    amount: float
    update_time: str
    # derived
    total_shares: float | None = None       # 亿股
    market_cap: float | None = None         # 亿元
    pe_ttm: float | None = None             # trailing PE


def _parse_wan(val: str) -> float:
    """Parse 万元 value to float."""
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def get_company_profile(ticker: str) -> CompanyProfile:
    """Fetch rich company profile from cninfo + Sina real-time quote."""

    # 1. cninfo profile (industry, business, history)
    try:
        cninfo = ak.stock_profile_cninfo(symbol=ticker)
        row = cninfo.iloc[0] if len(cninfo) > 0 else None
    except Exception:
        row = None

    # 2. Sina real-time quote (price, volume)
    try:
        sino = _fetch_sina_quote(ticker)
    except Exception:
        sino = {}

    # 3. Derive derived metrics
    reg_cap_raw = str(row["注册资金"]) if row is not None else "0"
    reg_cap_wan = _parse_wan(reg_cap_raw)
    total_shares = reg_cap_wan / 1e4 if reg_cap_wan > 0 else None  # 万元 → 亿股

    price = float(sino.get("最新价", 0) or 0)
    market_cap = None
    if total_shares and price > 0:
        market_cap = round(price * total_shares, 2)  # 亿元

    pe_ttm = None
    if market_cap:
        try:
            fin = get_financial_abstract(ticker, periods=6)
            annual = fin[fin["报告期"].str.contains("-12-31", na=False)]
            if len(annual) > 0:
                net_profit_raw = str(annual.iloc[0]["净利润"]).replace("亿", "").strip()
                net_profit = float(net_profit_raw)
                if net_profit > 0:
                    pe_ttm = round(market_cap / net_profit, 1)
        except Exception:
            pass

    return CompanyProfile(
        ticker=ticker,
        name=str(row["A股简称"]) if row is not None else sino.get("股票简称", ticker),
        name_en=str(row["英文名称"]) if row is not None else "",
        industry=str(row["所属行业"]) if row is not None else "公开资料未覆盖",
        market=str(row["所属市场"]) if row is not None else "",
        listing_date=str(row["上市日期"]) if row is not None else "",
        established_date=str(row["成立日期"]) if row is not None else "",
        legal_rep=str(row["法人代表"]) if row is not None else "",
        registered_capital=reg_cap_raw,
        main_business=str(row["主营业务"]) if row is not None else "",
        business_scope=str(row["经营范围"]) if row is not None else "",
        company_history=str(row["机构简介"]) if row is not None else "",
        website=str(row["官方网站"]) if row is not None else "",
        email=str(row["电子邮箱"]) if row is not None else "",
        address=str(row["注册地址"]) if row is not None else "",
        office=str(row["办公地址"]) if row is not None else "",
        latest_price=price,
        open=float(sino.get("今开", 0) or 0),
        prev_close=float(sino.get("昨收", 0) or 0),
        high=float(sino.get("今日最高", 0) or 0),
        low=float(sino.get("今日最低", 0) or 0),
        volume=float(sino.get("成交量(股)", 0) or 0),
        amount=float(sino.get("成交额(元)", 0) or 0),
        update_time=sino.get("更新时间", ""),
        total_shares=total_shares,
        market_cap=market_cap,
        pe_ttm=pe_ttm,
    )


# ---------------------------------------------------------------------------
# (unchanged)
# ---------------------------------------------------------------------------

def get_recent_news(ticker: str, limit: int = 10) -> pd.DataFrame:
    try:
        return ak.stock_news_em(symbol=ticker).head(limit)
    except Exception as exc:
        print(f"[fundamental] stock_news_em failed for {ticker}: {exc}")
        return pd.DataFrame()


_FIN_COLS = ["报告期", "营业总收入", "营业总收入同比增长率", "净利润", "净利润同比增长率"]


def get_financial_abstract(ticker: str, periods: int = 6) -> pd.DataFrame:
    df = ak.stock_financial_abstract_ths(symbol=ticker, indicator="按报告期")
    return (
        df[_FIN_COLS]
        .sort_values("报告期", ascending=False)
        .head(periods)
        .reset_index(drop=True)
    )


def get_announcements(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    return ak.stock_zh_a_disclosure_report_cninfo(
        symbol=ticker, market="沪深京", start_date=start_date, end_date=end_date
    )
