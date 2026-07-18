import argparse
import hashlib
import sys
import time as _time
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from analytics import (
    analyze_causal_chains,
    analyze_sources,
    build_analytics_text,
    build_peer_comparison_text,
    compute_financial_trends,
    score_guba_sentiment,
)
from collector.fetcher import fetch_article
from collector.fundamental import (
    get_announcements,
    get_company_profile,
    get_financial_abstract,
    get_industry_peers,
    get_peer_financials,
    get_recent_news,
)
from collector.guba import fetch_guba_posts
from collector.nxny import get_nxny_reports
from collector.pdf_fetcher import extract_announcement_pdf
from collector.search import (
    search_peer_comparison,
    search_supply_chain,
    search_topics,
)
from collector.xueqiu import (
    get_xueqiu_announcements,
    get_xueqiu_discussions,
)
from materials import load_materials
from report import render
from summarizer import (
    preprocess_materials,
    summarize_guba_sentiment,
    summarize_sections,
)

CACHE_DIR = Path("cache")
NEWS_FETCH_LIMIT = 12
ANNOUNCEMENT_WINDOW_DAYS = 90
TAVILY_PER_QUERY = 8
PDF_DOWNLOAD_LIMIT = 15
GUBA_POST_LIMIT = 80
GUBA_PAGES = 3


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


XUEQIU_DISCUSSION_LIMIT = 10
XUEQIU_ANNOUNCEMENT_LIMIT = 8
NXNY_REPORT_LIMIT = 8


def main(ticker: str, refresh: bool) -> None:
    print(f"[1/9] 抓取公司概况 {ticker}")
    profile = get_company_profile(ticker)
    company_name = profile.name
    print(f"    {company_name}")

    print(f"[2/9] 抓取财务摘要")
    financials = get_financial_abstract(ticker)
    print(f"    最新报告期：{financials.iloc[0]['报告期']}，共 {len(financials)} 期")

    urls_this_run: set[str] = set()
    end = date.today()
    start = end - timedelta(days=ANNOUNCEMENT_WINDOW_DAYS)

    print(f"[3/9] 抓取 T1 巨潮公告（近 {ANNOUNCEMENT_WINDOW_DAYS} 天）")
    announcements = get_announcements(
        ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    )
    pdf_count = 0
    for _, row in announcements.iterrows():
        url = row["公告链接"]
        title = row["公告标题"]
        pdate = row["公告时间"]
        path = _cache_path(ticker, url)
        if path.exists() and not refresh:
            urls_this_run.add(url)
            continue
        pdf_text = None
        if pdf_count < PDF_DOWNLOAD_LIMIT:
            pdf_text = extract_announcement_pdf(url, pdate)
            if pdf_text:
                pdf_count += 1
            _time.sleep(0.3)
        if pdf_text:
            body = f"公告标题：{title}\n公告日期：{pdate}\n\n{pdf_text}"
        else:
            body = f"公告标题：{title}\n公告日期：{pdate}\n（PDF 正文暂未提取）"
        _save_article(path, url, title, body)
        urls_this_run.add(url)
    print(f"    巨潮公告：{len(announcements)} 条（PDF 提取 {pdf_count} 条）")

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

    print(f"[4/9] 抓取 T3 新闻（akshare + Tavily 拓源，refresh={refresh}）")
    stats = {"hit": 0, "fresh": 0, "fail": 0, "dup": 0}

    news = get_recent_news(ticker, limit=NEWS_FETCH_LIMIT)
    for _, row in news.head(NEWS_FETCH_LIMIT).iterrows():
        s = _cache_or_fetch(ticker, row["新闻链接"], row["新闻标题"], refresh, urls_this_run)
        stats[s] += 1

    tavily_hits = search_topics(company_name, per_query=TAVILY_PER_QUERY)
    for url, title in tavily_hits:
        s = _cache_or_fetch(ticker, url, title, refresh, urls_this_run)
        stats[s] += 1
    print(f"    akshare {NEWS_FETCH_LIMIT} 条 + Tavily {len(tavily_hits)} 条 → "
          f"命中 {stats['hit']} / 新抓 {stats['fresh']} / 失败 {stats['fail']} / 去重 {stats['dup']}")

    print(f"[5/9] 抓取 T4 雪球讨论 + 股票报告网研报")
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

    print(f"[5.5/9] 股吧情绪聚合")
    guba_sentiment_url = f"guba://sentiment/{ticker}"
    guba_path = _cache_path(ticker, guba_sentiment_url)
    if guba_path.exists() and not refresh:
        urls_this_run.add(guba_sentiment_url)
        print(f"    使用缓存")
    else:
        guba_posts = fetch_guba_posts(ticker, limit=GUBA_POST_LIMIT, pages=GUBA_PAGES)
        if guba_posts:
            sentiment = summarize_guba_sentiment(ticker, guba_posts)
            if sentiment:
                _save_article(guba_path, guba_sentiment_url, "股吧情绪总结", sentiment)
                urls_this_run.add(guba_sentiment_url)
                print(f"    股吧帖子 {len(guba_posts)} 条 → 情绪总结已生成")
            else:
                print(f"    股吧帖子 {len(guba_posts)} 条 → LLM 聚合失败")
        else:
            print(f"    股吧帖子获取失败")

    print(f"[5.6/9] 产业链上下游搜索")
    supply_chain_url = f"supply://chain/{ticker}"
    supply_chain_path = _cache_path(ticker, supply_chain_url)
    if supply_chain_path.exists() and not refresh:
        urls_this_run.add(supply_chain_url)
        print(f"    使用缓存")
    else:
        sc_hits = search_supply_chain(company_name, per_query=TAVILY_PER_QUERY)
        for url, title in sc_hits:
            _cache_or_fetch(ticker, url, title, refresh, urls_this_run)
        if sc_hits:
            sc_blocks = [f"- {title} ({url})" for url, title in sc_hits]
            _save_article(supply_chain_path, supply_chain_url, "产业链上下游",
                          "以下为产业链上下游相关文章索引：\n" + "\n".join(sc_blocks))
            urls_this_run.add(supply_chain_url)
        print(f"    产业链搜索：{len(sc_hits)} 条")

    print(f"[5.7/9] 同业对比搜索 + 同行财务收集")
    peer_comparison_url = f"peer://comparison/{ticker}"
    peer_comparison_path = _cache_path(ticker, peer_comparison_url)
    peer_comparison_text = ""
    if peer_comparison_path.exists() and not refresh:
        urls_this_run.add(peer_comparison_url)
        print(f"    使用缓存")
    else:
        pc_hits = search_peer_comparison(company_name, per_query=TAVILY_PER_QUERY)
        for url, title in pc_hits:
            _cache_or_fetch(ticker, url, title, refresh, urls_this_run)

        peers = get_industry_peers(profile.industry, ticker)
        peer_fins = get_peer_financials(peers)
        peer_comparison_text = build_peer_comparison_text(
            company_name,
            str(financials.iloc[0]["营业总收入"]) if len(financials) > 0 else "—",
            str(financials.iloc[0].get("营业总收入同比增长率", "—")) if len(financials) > 0 else "—",
            str(financials.iloc[0]["净利润"]) if len(financials) > 0 else "—",
            str(financials.iloc[0].get("净利润同比增长率", "—")) if len(financials) > 0 else "—",
            peer_fins,
        )
        pc_body = f"同业对比搜索文章：{len(pc_hits)} 篇\n\n{peer_comparison_text}"
        _save_article(peer_comparison_path, peer_comparison_url, "同业比较", pc_body)
        urls_this_run.add(peer_comparison_url)
        print(f"    同业对比搜索：{len(pc_hits)} 篇，同行财务：{len(peer_fins)} 家")

    print(f"[5.8/9] 数据洞察分析")
    analytics_url = f"analytics://insight/{ticker}"
    analytics_path = _cache_path(ticker, analytics_url)
    if analytics_path.exists() and not refresh:
        urls_this_run.add(analytics_url)
        print(f"    使用缓存")
    else:
        guba_for_score = fetch_guba_posts(ticker, limit=GUBA_POST_LIMIT, pages=GUBA_PAGES)
        trends = compute_financial_trends(financials)
        sent_score = score_guba_sentiment(guba_for_score)
        raw_materials = load_materials(CACHE_DIR / ticker)
        src = analyze_sources(raw_materials)
        causal = analyze_causal_chains(company_name, raw_materials)

        if not peer_comparison_text and peer_comparison_path.exists():
            existing = peer_comparison_path.read_text(encoding="utf-8")
            peer_comparison_text = existing.split("\n\n", 1)[-1] if "\n\n" in existing else ""

        if not peer_comparison_text:
            peers = get_industry_peers(profile.industry, ticker)
            peer_fins = get_peer_financials(peers)
            peer_comparison_text = build_peer_comparison_text(
                company_name,
                str(financials.iloc[0]["营业总收入"]) if len(financials) > 0 else "—",
                str(financials.iloc[0].get("营业总收入同比增长率", "—")) if len(financials) > 0 else "—",
                str(financials.iloc[0]["净利润"]) if len(financials) > 0 else "—",
                str(financials.iloc[0].get("净利润同比增长率", "—")) if len(financials) > 0 else "—",
                peer_fins,
            )

        analytics_text = build_analytics_text(trends, sent_score, src, causal, peer_comparison_text)
        _save_article(analytics_path, analytics_url, "数据洞察", analytics_text)
        urls_this_run.add(analytics_url)
        parts = ["财务趋势", "情绪量化", "来源覆盖"]
        if causal:
            parts.append("因果链分析")
        if peer_comparison_text:
            parts.append("同业比较")
        print(f"    {' + '.join(parts)} 已生成")

    print(f"[6/9] 调用 LLM 生成六章节")
    materials = load_materials(CACHE_DIR / ticker, urls=urls_this_run)
    if not materials:
        print("素材库为空，终止")
        return
    print(f"    素材总数：{len(materials)}")
    materials, pre_usage = preprocess_materials(materials)
    if pre_usage["summarized_count"]:
        print(f"    预处理：{pre_usage['summarized_count']} 篇长文摘要 "
              f"（{pre_usage['prompt_tokens']}/{pre_usage['completion_tokens']} tokens）")
    llm_sections, usage = summarize_sections(ticker, materials)
    thinking_str = f" + {usage.get('reasoning_tokens', 0)} reasoning" if "reasoning_tokens" in usage else ""
    print(f"    token: input={usage['prompt_tokens']}, output={usage['completion_tokens']}{thinking_str}")

    print(f"[7/9] 渲染 Markdown 报告")
    path = render(ticker, profile, financials, llm_sections, materials)
    print(f"    已生成：{path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="股票调研报告生成")
    parser.add_argument("ticker", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新抓取")
    args = parser.parse_args()
    main(args.ticker, refresh=args.refresh)
