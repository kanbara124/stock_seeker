"""
股票智能调研系统 — Web 界面
启动方式：streamlit run app.py  或  双击 run.bat
"""

from __future__ import annotations

import io
import sys
import traceback
from datetime import date
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="股票智能调研系统",
    page_icon="📊",
    layout="wide",
)

# ── helpers ──────────────────────────────────────────────────────────────


def _run_pipeline(ticker: str, refresh: bool) -> tuple[str | None, str]:
    """Run the full pipeline and capture stdout. Returns (report_path, output_log)."""
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    try:
        from main import main as pipeline_main

        old_argv = sys.argv
        sys.argv = ["main.py", ticker]
        if refresh:
            sys.argv.append("--refresh")

        pipeline_main(ticker, refresh=refresh)

        sys.argv = old_argv
    except Exception:
        traceback.print_exc()
    finally:
        sys.stdout = old_stdout

    log = buf.getvalue()

    # find latest report
    reports_dir = Path("reports")
    if reports_dir.exists():
        candidates = sorted(
            reports_dir.glob(f"{ticker}_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return str(candidates[0]), log

    return None, log


def _load_previous_reports() -> list[Path]:
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return []
    return sorted(
        reports_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:20]


# ── sidebar ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 股票调研系统")
    st.markdown("输入 A 股代码，一键生成专业调研报告")

    ticker = st.text_input(
        "股票代码",
        value="600519",
        placeholder="例如：600519",
        max_chars=6,
        help="6 位 A 股代码，如 600519（贵州茅台）",
    )

    refresh = st.checkbox(
        "强制刷新（忽略缓存）",
        value=False,
        help="勾选后将重新抓取所有数据",
    )

    run_clicked = st.button("🚀 开始分析", type="primary", use_container_width=True)

    st.divider()

    st.markdown("### ⚙️ 快捷股票")
    quick_tickers = {
        "600519": "贵州茅台",
        "000858": "五粮液",
        "300750": "宁德时代",
        "002594": "比亚迪",
        "601318": "中国平安",
    }
    for t, name in quick_tickers.items():
        if st.button(f"{t} {name}", use_container_width=True):
            ticker = t
            st.session_state.ticker_input = t
            run_clicked = True

    st.divider()
    st.caption("v2.0 · 基于 DeepSeek + 多源数据")

# ── main area ─────────────────────────────────────────────────────────────

st.title("📈 股票智能调研报告")
st.caption("自动化搜集公告、新闻、研报、论坛讨论 → LLM 深度分析 → 可溯源报告")

tab1, tab2 = st.tabs(["🔍 生成报告", "📂 历史报告"])

# ── tab 1: generate ───────────────────────────────────────────────────────

with tab1:
    if run_clicked and ticker:
        if not ticker.isdigit() or len(ticker) != 6:
            st.error("请输入 6 位数字股票代码")
            st.stop()

        status_container = st.empty()

        with st.status(f"正在分析 {ticker}……", expanded=True) as status:
            st.write("数据采集 + LLM 分析中，请稍候（约 2-6 分钟）…")
            report_path, log = _run_pipeline(ticker, refresh)

            if report_path:
                status.update(
                    label=f"✅ {ticker} 分析完成！",
                    state="complete",
                    expanded=False,
                )
            else:
                status.update(
                    label=f"❌ {ticker} 分析失败",
                    state="error",
                    expanded=True,
                )

        # show log in expander
        if log:
            with st.expander("📋 运行日志", expanded=False):
                st.code(log, language="text")

        # render report
        if report_path:
            st.success(f"报告已生成：`{report_path}`")
            content = Path(report_path).read_text(encoding="utf-8")
            st.markdown(content, unsafe_allow_html=False)

            with open(report_path, "rb") as f:
                st.download_button(
                    "📥 下载 Markdown 报告",
                    f,
                    file_name=Path(report_path).name,
                    mime="text/markdown",
                )

            pdf_path = Path(report_path).with_suffix(".pdf")
            if pdf_path.exists():
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "📥 下载 PDF 报告",
                        f,
                        file_name=pdf_path.name,
                        mime="application/pdf",
                    )
        else:
            st.error("报告生成失败，请查看上方运行日志排查问题")

    elif run_clicked and not ticker:
        st.warning("请先输入股票代码")

    else:
        st.info("👈 在左侧输入股票代码，点击「开始分析」")

# ── tab 2: history ────────────────────────────────────────────────────────

with tab2:
    reports = _load_previous_reports()
    if not reports:
        st.info("暂无历史报告，先生成一份吧")
    else:
        st.markdown(f"共 {len(reports)} 份历史报告")
        for r in reports:
            parts = r.stem.split("_", 1)
            ticker_part = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            with st.expander(f"📄 {ticker_part} — {rest}", expanded=False):
                content = r.read_text(encoding="utf-8")
                st.markdown(content, unsafe_allow_html=False)
