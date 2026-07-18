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
from collector.nxny import get_nxny_reports
from collector.search import search_topics
from collector.xueqiu import (
    get_xueqiu_announcements,
    get_xueqiu_discussions,
)
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


def _cache_direct(
    ticker: str, url: str, title: str, body: str,
    refresh: bool, urls_seen: set[str],
) -> str:
    """Cache pre-extracted content directly (no HTTP fetch needed)."""
    if not url or url in urls_seen:
        return "dup"
    path = _cache_path(ticker, url)
    if path.exists() and not refresh:
        urls_seen.add(url)
        return "hit"
    _save_article(path, url, title, body)
    urls_seen.add(url)
    return "fresh"


XUEQIU_DISCUSSION_LIMIT = 5
XUEQIU_ANNOUNCEMENT_LIMIT = 5
NXNY_REPORT_LIMIT = 5


def main(ticker: str, refresh: bool) -> None:
    print(f"[1/7] 抓取公司概况 {ticker}")
    profile = get_company_profile(ticker)
    company_name = profile.loc[profile["item"] == "股票简称", "value"].iat[0]
    print(f"    {company_name}")

    print(f"[2/7] 抓取财务摘要")
    financials = get_financial_abstract(ticker)
    print(f"    最新报告期：{financials.iloc[0]['报告期']}，共 {len(financials)} 期")

    urls_this_run: set[str] = set()
    end = date.today()
    start = end - timedelta(days=ANNOUNCEMENT_WINDOW_DAYS)

    print(f"[3/7] 抓取 T1 巨潮公告（近 {ANNOUNCEMENT_WINDOW_DAYS} 天）")
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
    print(f"    巨潮公告：{len(announcements)} 条")

    xq_ann_stats = {"hit": 0, "fresh": 0, "dup": 0, "skip": 0}
    xq_announcements = get_xueqiu_announcements(
        ticker, limit=XUEQIU_ANNOUNCEMENT_LIMIT
    )
    for a in xq_announcements:
        if not a.get("url"):
            xq_ann_stats["skip"] += 1
            continue
        s = _cache_direct(
            ticker, a["url"], a["title"], a["text"],
            refresh, urls_this_run,
        )
        xq_ann_stats[s] += 1
    print(f"    雪球公告（年报/半年报/季报）：抓取 {len(xq_announcements)} 条 → "
          f"命中 {xq_ann_stats['hit']} / 新存 {xq_ann_stats['fresh']} / "
          f"去重 {xq_ann_stats['dup']} / 跳过 {xq_ann_stats['skip']}")

    print(f"[4/7] 抓取 T3 新闻（akshare + Tavily 拓源，refresh={refresh}）")
    stats = {"hit": 0, "fresh": 0, "fail": 0, "dup": 0}

    news = get_recent_news(ticker, limit=10)
    for _, row in news.head(NEWS_FETCH_LIMIT).iterrows():
        s = _cache_or_fetch(ticker, row["新闻链接"], row["新闻标题"], refresh, urls_this_run)
        stats[s] += 1

    tavily_hits = search_topics(company_name, per_query=TAVILY_PER_QUERY)
    for url, title in tavily_hits:
        s = _cache_or_fetch(ticker, url, title, refresh, urls_this_run)
        stats[s] += 1
    print(f"    akshare {NEWS_FETCH_LIMIT} 条 + Tavily {len(tavily_hits)} 条 → "
          f"命中 {stats['hit']} / 新抓 {stats['fresh']} / 失败 {stats['fail']} / 去重 {stats['dup']}")

    print(f"[5/7] 抓取 T4 雪球讨论 + 股票报告网研报")
    t4_stats = {"hit": 0, "fresh": 0, "dup": 0, "skip": 0}

    xq_discussions = get_xueqiu_discussions(
        ticker, limit=XUEQIU_DISCUSSION_LIMIT
    )
    for d in xq_discussions:
        if not d.get("url"):
            t4_stats["skip"] += 1
            continue
        s = _cache_direct(
            ticker, d["url"], d["title"], d["text"],
            refresh, urls_this_run,
        )
        t4_stats[s] += 1
    print(f"    雪球讨论：{len(xq_discussions)} 条")

    nxny_reports = get_nxny_reports(ticker, limit=NXNY_REPORT_LIMIT)
    for r in nxny_reports:
        if not r.get("url"):
            t4_stats["skip"] += 1
            continue
        s = _cache_direct(
            ticker, r["url"], r["title"], r["text"],
            refresh, urls_this_run,
        )
        t4_stats[s] += 1
    print(f"    股票报告网研报：{len(nxny_reports)} 条")
    print(f"    T4 合计 → 命中 {t4_stats['hit']} / 新存 {t4_stats['fresh']} / "
          f"去重 {t4_stats['dup']} / 跳过 {t4_stats['skip']}")

    print(f"[6/7] 调用 LLM 生成三章节")
    materials = load_materials(CACHE_DIR / ticker, urls=urls_this_run)
    if not materials:
        print("素材库为空，终止")
        return
    print(f"    素材总数：{len(materials)}")
    llm_sections, usage = summarize_sections(ticker, materials)
    print(f"    token: input={usage['prompt_tokens']}, output={usage['completion_tokens']}")

    print(f"[7/7] 渲染 Markdown 报告")
    path = render(ticker, profile, financials, llm_sections, materials)
    print(f"    已生成：{path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="股票调研报告生成")
    parser.add_argument("ticker", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新抓取")
    args = parser.parse_args()
    main(args.ticker, refresh=args.refresh)
