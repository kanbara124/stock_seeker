import argparse
import hashlib
import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from collector.fetcher import fetch_article
from collector.fundamental import (
    get_announcements,
    get_company_profile,
    get_financial_abstract,
    get_recent_news,
)
from collector.search import search_topics
from materials import load_materials
from report import render
from summarizer import summarize_sections

CACHE_DIR = Path("cache")
NEWS_FETCH_LIMIT = 5
ANNOUNCEMENT_WINDOW_DAYS = 90
TAVILY_PER_QUERY = 5


def _cache_path(ticker: str, url: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    return CACHE_DIR / ticker / f"{key}.txt"


def _save_article(path: Path, url: str, title: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{title}\n{url}\n\n{text}\n", encoding="utf-8")


def _cache_or_fetch(
    ticker: str, url: str, title: str, refresh: bool, urls_seen: set[str]
) -> str:
    if url in urls_seen:
        return "dup"
    path = _cache_path(ticker, url)
    if path.exists() and not refresh:
        urls_seen.add(url)
        return "hit"
    result = fetch_article(url)
    if result is None:
        return "fail"
    _, body = result
    _save_article(path, url, title, body)
    urls_seen.add(url)
    return "fresh"


def main(ticker: str, refresh: bool) -> None:
    print(f"[1/6] 抓取公司概况 {ticker}")
    profile = get_company_profile(ticker)
    company_name = profile.loc[profile["item"] == "股票简称", "value"].iat[0]
    print(f"    {company_name}")

    print(f"[2/6] 抓取财务摘要")
    financials = get_financial_abstract(ticker)
    print(f"    最新报告期：{financials.iloc[0]['报告期']}，共 {len(financials)} 期")

    print(f"[3/6] 抓取 T1 巨潮公告（近 {ANNOUNCEMENT_WINDOW_DAYS} 天）")
    urls_this_run: set[str] = set()
    end = date.today()
    start = end - timedelta(days=ANNOUNCEMENT_WINDOW_DAYS)
    announcements = get_announcements(
        ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    )
    for _, row in announcements.iterrows():
        url = row["公告链接"]
        title = row["公告标题"]
        pdate = row["公告时间"]
        path = _cache_path(ticker, url)
        if path.exists() and not refresh:
            urls_this_run.add(url)
            continue
        body = f"公告标题：{title}\n公告日期：{pdate}\n（正文暂未提取，M5.5 阶段接入 PyMuPDF 解析 PDF 后补齐）"
        _save_article(path, url, title, body)
        urls_this_run.add(url)
    print(f"    T1 公告：{len(announcements)} 条")

    print(f"[4/6] 抓取 T3 新闻（akshare + Tavily 拓源，refresh={refresh}）")
    stats = {"hit": 0, "fresh": 0, "fail": 0, "dup": 0}

    news = get_recent_news(ticker, limit=10)
    for _, row in news.head(NEWS_FETCH_LIMIT).iterrows():
        s = _cache_or_fetch(ticker, row["新闻链接"], row["新闻标题"], refresh, urls_this_run)
        stats[s] += 1

    tavily_hits = search_topics(company_name, per_query=TAVILY_PER_QUERY)
    for url, title in tavily_hits:
        s = _cache_or_fetch(ticker, url, title, refresh, urls_this_run)
        stats[s] += 1
    print(f"    akshare 5 条 + Tavily {len(tavily_hits)} 条 → 命中 {stats['hit']} / 新抓 {stats['fresh']} / 失败 {stats['fail']} / 去重 {stats['dup']}")

    print(f"[5/6] 调用 LLM 生成三章节")
    materials = load_materials(CACHE_DIR / ticker, urls=urls_this_run)
    if not materials:
        print("素材库为空，终止")
        return
    print(f"    素材总数：{len(materials)}")
    llm_sections, usage = summarize_sections(ticker, materials)
    print(f"    token: input={usage['prompt_tokens']}, output={usage['completion_tokens']}")

    print(f"[6/6] 渲染 Markdown 报告")
    path = render(ticker, profile, financials, llm_sections, materials)
    print(f"    已生成：{path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="股票调研报告生成")
    parser.add_argument("ticker", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新抓取")
    args = parser.parse_args()
    main(args.ticker, refresh=args.refresh)
