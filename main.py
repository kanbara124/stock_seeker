import hashlib
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from collector.fetcher import fetch_article
from collector.fundamental import get_company_profile, get_recent_news
from materials import load_materials
from summarizer import summarize

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
    print(f"=== 公司概况 {ticker} ===")
    profile = get_company_profile(ticker)
    print(profile.to_string(index=False))

    print(f"\n=== 近期新闻（前 10 条） ===")
    news = get_recent_news(ticker, limit=10)
    print(news.to_string(index=False))

    print(f"\n=== 抓取正文（前 {FETCH_LIMIT} 条） ===")
    success = 0
    for _, row in news.head(FETCH_LIMIT).iterrows():
        url = row["新闻链接"]
        result = fetch_article(url)
        if result is None:
            print(f"[-] {url}")
            continue
        _, body = result
        title = row["新闻标题"]
        path = _save_article(ticker, url, title, body)
        print(f"[+] {path} ({len(body)} chars) — {title[:40]}")
        success += 1
    print(f"抓取完成：{success}/{FETCH_LIMIT} 成功")

    print(f"\n=== LLM 汇总 ===")
    materials = load_materials(CACHE_DIR / ticker)
    if not materials:
        print("素材库为空，跳过 LLM 汇总")
        return
    summary, usage = summarize(ticker, materials)
    print(summary)
    print(f"\n[token] input={usage['prompt_tokens']}, output={usage['completion_tokens']}")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "600519"
    main(ticker)
