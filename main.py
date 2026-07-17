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


def _save_article(ticker: str, url: str, title: str, text: str) -> Path:
    out_dir = CACHE_DIR / ticker
    out_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(url.encode()).hexdigest()[:12]
    path = out_dir / f"{key}.txt"
    path.write_text(f"{title}\n{url}\n\n{text}\n", encoding="utf-8")
    return path


def main(ticker: str) -> None:
    print(f"[1/4] 抓取公司概况 {ticker}")
    profile = get_company_profile(ticker)

    print(f"[2/4] 抓取新闻列表并下载正文（前 {FETCH_LIMIT} 条）")
    news = get_recent_news(ticker, limit=10)
    urls_this_run: set[str] = set()
    for _, row in news.head(FETCH_LIMIT).iterrows():
        url = row["新闻链接"]
        result = fetch_article(url)
        if result is None:
            print(f"    [-] {url}")
            continue
        _, body = result
        _save_article(ticker, url, row["新闻标题"], body)
        urls_this_run.add(url)
    print(f"    抓取完成：{len(urls_this_run)}/{FETCH_LIMIT}")

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
    ticker = sys.argv[1] if len(sys.argv) > 1 else "600519"
    main(ticker)
