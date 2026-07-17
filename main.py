import hashlib
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from collector.fetcher import fetch_article
from collector.fundamental import get_company_profile, get_recent_news

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
    urls = news["新闻链接"].head(FETCH_LIMIT).tolist()
    success = 0
    for url in urls:
        result = fetch_article(url)
        if result is None:
            print(f"[-] {url}")
            continue
        title, text = result
        path = _save_article(ticker, url, title, text)
        print(f"[+] {path} ({len(text)} chars) — {title[:40]}")
        success += 1
    print(f"\n抓取完成：{success}/{FETCH_LIMIT} 成功")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "600519"
    main(ticker)
