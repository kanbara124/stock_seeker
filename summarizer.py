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


_GUBA_PROMPT = """你是股市舆情分析师。根据以下 {ticker} 股吧帖子的标题和互动数据，总结散户情绪。

帖子数据格式：每行一条 【标题】（阅读数 评论数 用户：昵称）

请输出一段 150-250 字的总结，包含：
1. **多空比例**：估算看多/看空/中性帖子的比例
2. **热议话题**：列出 2-3 个讨论最多的话题
3. **整体情绪**：一句话概括散户当前情绪倾向

注意：
- 仅依据帖子标题判断多空，不要编造
- 如果帖子样本不足（少于 5 条），注明"样本量有限"
- 不要给出投资建议

帖子列表：
{guba_posts}
"""


def summarize_guba_sentiment(ticker: str, posts: list) -> str:
    """Aggregate guba post titles into a sentiment summary.

    Args:
        ticker: stock ticker
        posts: list of GubaPost or dicts with one_line() / title/reads/comments/user info

    Returns:
        A 150-250 char Chinese sentiment summary.
    """
    if not posts:
        return ""

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置（检查 .env）")

    lines = []
    for p in posts:
        if hasattr(p, "one_line"):
            lines.append(p.one_line())
        else:
            title = p.get("title", "")
            reads = p.get("reads", 0)
            comments = p.get("comments", 0)
            user = p.get("user_name", p.get("user", ""))
            lines.append(
                f"【{title}】（{reads}阅读 {comments}评论 用户：{user}）"
            )

    client = OpenAI(api_key=api_key, base_url=_BASE_URL)
    prompt = _GUBA_PROMPT.format(
        ticker=ticker,
        guba_posts="\n".join(lines[:50]),
    )
    resp = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content
