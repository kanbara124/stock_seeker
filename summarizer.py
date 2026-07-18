import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI

from materials import Material

load_dotenv()

_MODEL = "deepseek-v4-flash"
_BASE_URL = "https://api.deepseek.com"
_MAX_CHARS_PER_MATERIAL = 3000    # beyond this → pre-summarize
_LLM_TIMEOUT = 120                # seconds, per-request cutoff
_PRE_SUMMARIZE_MAX_WORKERS = 4    # parallel pre-summarization threads


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置（检查 .env）")
    return OpenAI(api_key=api_key, base_url=_BASE_URL)


def _call_llm(
    messages: list[dict],
    *,
    thinking: bool = False,
    temperature: float = 0.3,
) -> tuple[str, dict]:
    """Unified LLM call.  Returns (text, usage_dict)."""
    kwargs: dict = {
        "model": _MODEL,
        "messages": messages,
        "temperature": temperature,
        "timeout": _LLM_TIMEOUT,
    }
    if thinking:
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

    resp = _client().chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    usage = {
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
    }
    if resp.usage and hasattr(resp.usage, "completion_tokens_details"):
        details = resp.usage.completion_tokens_details
        if hasattr(details, "reasoning_tokens"):
            usage["reasoning_tokens"] = details.reasoning_tokens
    return text, usage


# ---------------------------------------------------------------------------
# material pre-processing (non-thinking, cost-minimal)
# ---------------------------------------------------------------------------

_PRE_SUMMARIZE_PROMPT = (
    "请将以下投资研究材料压缩为 400-800 字的要点摘要。"
    "保留所有具体数字（金额、百分比、日期、估值）、关键事实和来源信息。"
    "删除重复内容、修辞性语言和无关背景。"
    "直接输出摘要，不要加任何前言。\n\n"
    "原文：\n{text}"
)


def pre_summarize_material(text: str) -> tuple[str, dict]:
    """Summarize a single long material into a shorter abstract.

    Only called for materials exceeding the character threshold.
    Uses non-thinking mode for minimal cost.
    """
    prompt = _PRE_SUMMARIZE_PROMPT.format(text=text)
    return _call_llm(
        [{"role": "user", "content": prompt}],
        thinking=False,
        temperature=0.2,
    )


def _pre_summarize_one(m: Material) -> Material:
    if len(m.text) <= _MAX_CHARS_PER_MATERIAL:
        return m
    summary, _ = pre_summarize_material(m.text)
    if summary:
        return Material(n=m.n, title=m.title, url=m.url, text=summary)
    return m


def preprocess_materials(materials: list[Material]) -> tuple[list[Material], dict]:
    """Run pre-summarization on long materials in parallel.  Returns modified list + cost.

    Materials whose text exceeds _MAX_CHARS_PER_MATERIAL are replaced with
    shortened versions (original URL and title preserved).
    """
    total_usage: dict = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "summarized_count": 0,
    }

    long_indices = [i for i, m in enumerate(materials) if len(m.text) > _MAX_CHARS_PER_MATERIAL]
    if not long_indices:
        return list(materials), total_usage

    with ThreadPoolExecutor(max_workers=_PRE_SUMMARIZE_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_pre_summarize_one, materials[i]): i
            for i in long_indices
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                materials[idx] = future.result()
                total_usage["summarized_count"] += 1
            except Exception:
                pass

    return materials, total_usage


# ---------------------------------------------------------------------------
# main report generation (thinking mode)
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """你是资深行业研究员。根据下列 {n} 篇材料，为股票 {ticker} 撰写一份专业调研报告的七
个章节。请像雪球深度分析帖一样思考：挖掘数据背后的逻辑，串联事件中的因果，让
读者理解"发生了什么、为什么重要、接下来怎么看"。

═══════════════════════════════════════
               写作铁律
═══════════════════════════════════════
0. **禁止任何开场白、导语、问候语或自我介绍。输出必须以第一个章节标题 "## 三、业务与行业分析" 开头，前面不得有任何文字。**
1. 每一句事实性陈述必须标注来源编号 [n]，多来源写 [1][3]。不标注 = 编造。
2. 优先使用材料中的具体数字（增长率、金额、百分比、吨/辆/元），绝不泛泛而谈。
3. 材料中没出现的逻辑链条，写"公开资料未涵盖该维度"，禁止脑补。
4. 语言客观、冷静，禁止"强烈看好""必将爆发""千载难逢"等煽动性措辞。
5. 每个子标题必须是信息量密集的判断句，而非空洞标签（例："飞天茅台年内两度提价，合同价累计上调200元/瓶" 而非 "价格调整"）。
6. 章节标题（含编号 ## 三、标题）与层级不得改动，不得增加新的 ## 级标题。
7. **宁漏大勿漏快**：若公司有多个业务板块，必须全部覆盖。当前收入占比最大的板块 ≠ 最重要的板块。对增速高、成长潜力大的板块（即使收入占比小），要给予不低于收入大板块的篇幅和分析深度。材料中出现的各板块增速数据，必须逐一列出并对比。

═══════════════════════════════════════
               输出模板
═══════════════════════════════════════

## 三、业务与行业分析

（350-600 字）

要求：
- **第一步：拆全**。列出公司所有业务板块/产品线，标注每个板块的收入占比和同比增速 [来源编号]。不可遗漏任何材料中提到的板块。
- **第二步：比速**。比较各板块的增速差异。增速最高和最低的板块分别是什么？增速差异反映了怎样的战略重心转移或行业景气分化？
- **第三步：看势**。对高增速板块（即使收入占比目前较小），深入分析：增长驱动力是什么（国产替代？下游景气？技术突破？大客户导入？）可持续性如何？
- **第四步：定性**。对收入占比大但增速放缓的板块，分析原因（行业见顶？竞争加剧？公司战略收缩？）。
- 指出公司所处行业的当前阶段（景气/调整/转型），引用材料中的行业数据佐证。
- 若材料仅覆盖部分维度，明确说明"公开资料未覆盖 X 方面"。

## 四、近期动态

（400-600 字）

要求：
- 不是时间线流水账。按**主题线索**组织（如：价格策略 / 资本运作 / 人事与治理 / 经营业绩）。
- 每个主题下串接 2-3 件相关事件，点明因果关系："A 发生了 → 导致 B → 反映 C 趋势"。
- 关键事件必须用具体数字说话（"每股派息 28.02 元，较上年变化 X%"）。
- 区分"事实"与"解读"：事实标注来源，解读用"反映/意味着/可能表明"等措辞。
- 对相互矛盾的事件（如同时涨价和销量下滑），正面点出张力而非回避。
- **覆盖要全**：若近期动态涉及多个业务板块，不可只讲收入占比最大的一个。

## 五、年内新发展

（400-600 字）

要求：
- 聚焦公司**近一年内**出现的重大发展和变化，而非日常经营细节。
- **增长视角优先**：优先关注那些增速快、边际变化大的板块。一个收入占比 30% 但增速 50% 的板块，比一个收入占比 70% 但增速 5% 的板块更值得作为"新发展"来写。
- 至少覆盖以下 2-3 个维度（按**增长潜力和变化幅度**选择，而非按收入规模选择）：
  - **新产品 / 新业务**：公司推出了什么新产品或进入了什么新业务领域？量产/商业化进度如何 [来源编号]？
  - **新产线 / 产能扩张**：是否有新工厂投产、产线升级、产能爬坡？投资规模和预计产值 [来源编号]？
  - **技术突破**：公司取得了哪些关键技术突破或研发里程碑？对行业竞争格局的影响 [来源编号]？
  - **新市场 / 新客户**：是否进入新的地理市场或拿下重要大客户？订单规模和战略意义 [来源编号]？
  - **新模式 / 新战略**：公司是否调整了商业模式或战略方向（如：从设备销售转向服务收费、从国内转向出海、从单品转向平台）？
- 每个维度要写清"发生了什么变化 → 变化前后的对比 → 为什么重要"。
- 若材料中缺乏相关信息，写"公开资料未充分覆盖该公司近一年的新发展动向"。

## 六、市场观点与分歧

（400-600 字）

要求：
- 以**多空对话**结构呈现，而非分列清单。格式示例：

  **看多逻辑**（来源：券商研报 [X] / 雪球 [Y]）
  - 核心论点 + 论据 [来源编号]
  
  **看空逻辑**（来源：媒体 [Z] / 股吧情绪 [W]）
  - 核心质疑 + 论据 [来源编号]
  
  **分歧焦点**：多空双方在哪个关键假设上存在根本分歧？

- 机构观点必须注明券商名称、评级、目标价（如有）；散户情绪引用股吧/雪球总结。
- 若多空失衡（如只有看多研报），用"公开资料中，看空观点主要来自……"的方式补足。
- 禁止用"公开资料未覆盖空方立场"一句话带过——至少要尝试从新闻/论坛/数据中挖掘反面信号。

## 七、风险与前瞻

（300-400 字）

要求：
- 风险按**发生概率 × 影响程度**排序，而非面面俱到。
- 每条风险写清触发条件："若 X 持续/发生，则 Y 可能受影响 [来源]"。
- 最后附一段**短期展望**（100 字内）：基于现有材料中的趋势信号（管理层指引、行业数据、
  机构预测等），合理推演未来 6-12 个月的可能情景。注明"以下为基于公开信息的推演，不构成预测"。
- 若材料中缺乏前瞻数据，写"公开材料未提供足够信息用于短期展望"。

## 八、产业链上下游分析

（300-400 字）

要求：
- 明确公司在产业链中的定位（上游资源 / 中游制造 / 下游渠道 / 平台型等）[来源编号]。
- 列出上游的关键供应商或原材料，说明供应集中度和议价能力；若材料中提到具体供应商名称或上游公司，必须注明 [来源编号]。
- 列出下游的主要客户或应用场景，说明客户集中度和需求稳定性；若材料中包含大客户名称或下游行业数据，必须引用 [来源编号]。
- 分析成本传导能力：原材料价格波动对公司利润的影响程度，以及公司能否将成本转嫁给下游。
- 在合适的情况下，提及产业链中涉及的具体上市公司及其与目标公司的业务关联。
- 若材料仅覆盖部分环节，明确说明"公开资料未涵盖 X 环节"。

## 九、同业比较

（400-500 字）

要求：
- 选出 3-5 家与目标公司业务模式、行业定位最接近的上市公司作为对标对象，逐一列出股票代码和简称 [来源编号]。
- 从材料中的数据洞察（同业比较自动化表格）中，比较各公司的核心财务指标：营收规模、营收增速、净利润、净利润增速、净利率。
- 分析目标公司在行业中的相对定位：是龙头、追赶者还是利基玩家？引用市占率、产能规模、品牌影响力等具体依据 [来源编号]。
- 比较各公司的战略差异（如：高端化 vs 性价比、自营 vs 加盟、重资产 vs 轻资产、多元化 vs 聚焦），说明不同路径的优劣。
- 对目标公司在同业中的竞争优势和短板做出有依据的判断，避免泛泛而论。
- 若材料中缺乏可比的同业财务数据，基于定性信息进行分析并注明"定量比较受限于公开数据可得性"。

═══════════════════════════════════════
               材料清单
═══════════════════════════════════════
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
    """Generate the main report sections using thinking mode for deeper analysis."""
    prompt = _PROMPT_TEMPLATE.format(
        n=len(materials),
        ticker=ticker,
        materials=_format_materials(materials),
    )
    text, usage = _call_llm(
        [{"role": "user", "content": prompt}],
        thinking=True,
        temperature=0.3,
    )
    text = re.sub(r'^.*?(?=##\s)', '', text, count=1, flags=re.DOTALL)
    return text, usage


# ---------------------------------------------------------------------------
# guba sentiment (non-thinking)
# ---------------------------------------------------------------------------

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
    """Aggregate guba post titles into a sentiment summary (non-thinking)."""
    if not posts:
        return ""

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

    prompt = _GUBA_PROMPT.format(
        ticker=ticker,
        guba_posts="\n".join(lines[:50]),
    )
    text, _ = _call_llm(
        [{"role": "user", "content": prompt}],
        thinking=False,
        temperature=0.3,
    )
    return text
