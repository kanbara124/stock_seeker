import argparse
import hashlib
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from collector.fetcher import fetch_article
from collector.fundamental import get_company_profile, get_recent_news
from materials import load_materials
from report import render
from summarizer import summarize_sections

CACHE_DIR = Path("cache")
FETCH_LIMIT = 5


def _cache_path(ticker: str, url: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    return CACHE_DIR / ticker / f"{key}.txt"


def _save_article(path: Path, url: str, title: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{title}\n{url}\n\n{text}\n", encoding="utf-8")


def main(ticker: str, refresh: bool) -> None:
    print(f"[1/4] 抓取公司概况 {ticker}")
    profile = get_company_profile(ticker)

    print(f"[2/4] 抓取新闻列表并下载正文（前 {FETCH_LIMIT} 条，refresh={refresh}）")
    news = get_recent_news(ticker, limit=10)
    urls_this_run: set[str] = set()
    hits = fresh = fails = 0
    for _, row in news.head(FETCH_LIMIT).iterrows():
        url = row["新闻链接"]
        path = _cache_path(ticker, url)
        if path.exists() and not refresh:
            urls_this_run.add(url)
            hits += 1
            print(f"    [·] cached  {url}")
            continue
        result = fetch_article(url)
        if result is None:
            fails += 1
            print(f"    [-] failed  {url}")
            continue
        _, body = result
        _save_article(path, url, row["新闻标题"], body)
        urls_this_run.add(url)
        fresh += 1
        print(f"    [+] fetched {url}")
    print(f"    汇总：命中缓存 {hits}，新抓取 {fresh}，失败 {fails}")

    print(f"[3/4] 调用 LLM 生成三章节")
    materials = load_materials(CACHE_DIR / ticker, urls=urls_this_run)
    if not materials:
        print("素材库为空，终止")
        return
    llm_sections, usage = summarize_sections(ticker, materials)
    print(f"    token: input={usage['prompt_tokens']}, output={usage['completion_tokens']}")

    print(f"[4/4] 渲染 Markdown 报告")
    path = render(ticker, profile, llm_sections, materials)
    print(f"    已生成：{path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="股票调研报告生成")
    parser.add_argument("ticker", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，强制重新抓取")
    args = parser.parse_args()
    main(args.ticker, refresh=args.refresh)
