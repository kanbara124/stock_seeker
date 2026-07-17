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
