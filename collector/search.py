import os

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

_ALLOWED_DOMAINS = [
    "xueqiu.com",
    "hibor.com.cn",
    "guba.eastmoney.com",
    "21jingji.com",
    "caixin.com",
    "yicai.com",
    "jiemian.com",
    "wallstreetcn.com",
    "cs.com.cn",
    "cnstock.com",
    "stcn.com",
    "cls.cn",
    "bjnews.com.cn",
    "thepaper.cn",
]

SEARCH_TEMPLATES = [
    "{name} 研报 观点",
    "{name} 深度分析",
    "{name} 风险 争议",
]

SUPPLY_CHAIN_TEMPLATES = [
    "{name} 产业链 上游 下游 供应商",
    "{name} 原材料 客户 销售渠道",
]

PEER_COMPARISON_TEMPLATES = [
    "{name} 同行 对比 竞争对手",
    "{name} 行业 对标 估值 比较",
]


def _client() -> TavilyClient:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY 未设置（检查 .env）")
    return TavilyClient(api_key=key)


def search_urls(query: str, max_results: int = 5) -> list[tuple[str, str]]:
    resp = _client().search(
        query=query,
        max_results=max_results,
        include_domains=_ALLOWED_DOMAINS,
    )
    results = []
    for r in resp.get("results", []):
        url = r.get("url", "")
        if "xueqiu.com/S/" in url:
            continue
        results.append((url, r.get("title") or ""))
    return results


def _search(name: str, templates: list[str], per_query: int) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for tpl in templates:
        for url, title in search_urls(tpl.format(name=name), max_results=per_query):
            if url in seen:
                continue
            seen.add(url)
            out.append((url, title))
    return out


def search_topics(name: str, per_query: int = 5) -> list[tuple[str, str]]:
    return _search(name, SEARCH_TEMPLATES, per_query)


def search_supply_chain(name: str, per_query: int = 5) -> list[tuple[str, str]]:
    return _search(name, SUPPLY_CHAIN_TEMPLATES, per_query)


def search_peer_comparison(name: str, per_query: int = 5) -> list[tuple[str, str]]:
    return _search(name, PEER_COMPARISON_TEMPLATES, per_query)
