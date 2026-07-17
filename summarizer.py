import os

from dotenv import load_dotenv
from openai import OpenAI

from materials import Material

load_dotenv()

_MODEL = "deepseek-chat"
_BASE_URL = "https://api.deepseek.com"

_PROMPT_TEMPLATE = """你是股票调研助手。根据下列 {n} 篇材料，撰写一段关于股票 {ticker} 的近期动态总结（300-500 字）。

严格要求：
1. 只能使用材料中的内容；材料未提及的事实必须写"公开资料未提及"，不得编造
2. 每个事实性结论后必须标注来源编号，格式 [n]（n 为材料编号）；同一句多个来源写成 [1][3]
3. 语言简洁客观，避免情绪化表述

材料清单：
{materials}
"""


def _format_materials(materials: list[Material]) -> str:
    blocks = []
    for m in materials:
        blocks.append(
            f"[{m.n}] 标题：{m.title or '(无)'}\n    链接：{m.url}\n    正文：{m.text}"
        )
    return "\n\n".join(blocks)


def summarize(ticker: str, materials: list[Material]) -> tuple[str, dict]:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置（检查 .env）")

    client = OpenAI(api_key=api_key, base_url=_BASE_URL)
    prompt = _PROMPT_TEMPLATE.format(
        n=len(materials),
        ticker=ticker,
        materials=_format_materials(materials),
    )
    resp = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    usage = {
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
    }
    return resp.choices[0].message.content, usage
