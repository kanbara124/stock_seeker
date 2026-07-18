"""
东方财富股吧 post collector.

Parses the ``article_list`` JS variable embedded in the guba list page
(no JS rendering / API key required).  Returns post titles + engagement
metadata for sentiment aggregation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LIST_URL = "https://guba.eastmoney.com/list,{ticker}.html"
_POST_URL = "https://guba.eastmoney.com/news,{ticker},{post_id}.html"

_article_list_re = re.compile(
    r"var article_list\s*=\s*(\{.+?\});\s*var", re.DOTALL
)


@dataclass
class GubaPost:
    post_id: str
    title: str
    user_name: str
    reads: int
    comments: int
    post_type: int
    publish_time: str
    url: str

    def one_line(self) -> str:
        return (
            f"【{'讨论' if self.post_type == 205 else '资讯'}】"
            f"{self.title} "
            f"（{self.reads}阅读 {self.comments}评论 "
            f"用户：{self.user_name or '未知'}）"
        )


def fetch_guba_posts(ticker: str, limit: int = 50) -> list[GubaPost]:
    """Fetch recent guba posts for a stock ticker.

    Returns a mix of user discussions (type 205, prioritized) and
    high-engagement news items (type 100), up to *limit* posts.
    """
    url = _LIST_URL.format(ticker=ticker)
    s = requests.Session()
    s.headers.update({"User-Agent": _UA})

    try:
        r = s.get(url, timeout=15)
        r.encoding = r.apparent_encoding
    except Exception:
        return []

    m = _article_list_re.search(r.text)
    if not m:
        return []

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    items = data.get("re", [])
    if not items:
        return []

    posts: list[GubaPost] = []
    for item in items:
        pid = str(item.get("post_id", ""))
        title = (item.get("post_title") or "").strip()
        user = (item.get("user_nickname") or "").strip()
        reads = int(item.get("post_click_count") or 0)
        comments = int(item.get("post_comment_count") or 0)
        post_type = int(item.get("stockbar_type") or 0)
        publish_time = str(item.get("post_publish_time") or "")

        if not pid or not title:
            continue

        posts.append(
            GubaPost(
                post_id=pid,
                title=title,
                user_name=user,
                reads=reads,
                comments=comments,
                post_type=post_type,
                publish_time=publish_time,
                url=_POST_URL.format(ticker=ticker, post_id=pid),
            )
        )

    # Prioritize discussions, then add high-engagement news
    discussions = [p for p in posts if p.post_type == 205]
    news_sorted = sorted(
        [p for p in posts if p.post_type != 205],
        key=lambda p: (p.comments, p.reads),
        reverse=True,
    )

    selected = discussions[:]
    for n in news_sorted:
        if len(selected) >= limit:
            break
        selected.append(n)

    return selected
