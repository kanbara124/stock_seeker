import os

from dotenv import load_dotenv
from openai import OpenAI

from materials import Material

load_dotenv()

_MODEL = "deepseek-chat"
_BASE_URL = "https://api.deepseek.com"

_PROMPT_TEMPLATE = """你是股票调研助手。根据下列 {n} 篇材料，为股票 {ticker} 撰写以下三个报告章节。

严格要求：
1. 只能使用材料中的内容；未在材料中出现的信息必须写"公开资料未提及"，绝不编造
2. 每个事实性结论后必须标注来源编号，格式 [n]（n 为材料编号）；多来源写作 [1][3]
3. 严格按下面的 Markdown 模板输出，章节标题（含编号）与层级不得改动，也不得增加其他标题
4. 语言简洁客观，避免情绪化表述与投资建议

输出模板：
```
## 三、近期动态

（此处填写基于材料的公告与新闻事件要点，200-400 字）

## 四、市场观点与分歧

（此处填写研报观点、机构与散户的看多/看空立场对比。若材料未覆盖多空双方，明确说明"公开资料仅覆盖 X 立场"）

## 五、风险提示

（此处按材料内容归纳经营/行业/市场风险，逐条列出）
```

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


def summarize_sections(ticker: str, materials: list[Material]) -> tuple[str, dict]:
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
