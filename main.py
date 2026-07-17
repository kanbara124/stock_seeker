import sys

sys.stdout.reconfigure(encoding="utf-8")

from collector.fundamental import get_company_profile, get_recent_news


def main(ticker: str) -> None:
    print(f"=== 公司概况 {ticker} ===")
    profile = get_company_profile(ticker)
    print(profile.to_string(index=False))

    print(f"\n=== 近期新闻（前 10 条） ===")
    news = get_recent_news(ticker, limit=10)
    print(news.to_string(index=False))


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "600519"
    main(ticker)
