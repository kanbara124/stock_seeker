import akshare as ak
import pandas as pd

from collector.rate_limit import safe_get

_SINA_FIELDS = [
    "股票简称", "今开", "昨收", "最新价", "今日最高", "今日最低",
    "竞买价", "竞卖价", "成交量(股)", "成交额(元)",
]


def get_company_profile(ticker: str) -> pd.DataFrame:
    prefix = "sh" if ticker.startswith("6") else "sz"
    r = safe_get(
        f"https://hq.sinajs.cn/list={prefix}{ticker}",
        headers={"Referer": "https://finance.sina.com.cn"},
    )
    r.encoding = "gbk"
    payload = r.text.split('"', 2)[1]
    values = payload.split(",")
    rows = list(zip(_SINA_FIELDS, values[: len(_SINA_FIELDS)]))
    rows.append(("更新时间", f"{values[30]} {values[31]}"))
    return pd.DataFrame(rows, columns=["item", "value"])


def get_recent_news(ticker: str, limit: int = 10) -> pd.DataFrame:
    return ak.stock_news_em(symbol=ticker).head(limit)


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
