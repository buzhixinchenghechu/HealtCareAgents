# -*- coding: utf-8 -*-
"""
阿片类药物处方辅助决策 & 医学生培训系统
Web版 - 基于 Streamlit + 通义千问 API
"""

import streamlit as st
import json
import os
import re
from openai import OpenAI
from datetime import datetime

# ─────────────────────────────────────────────
# 页面基础配置
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="阿片类药物智能辅助系统",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# API 客户端初始化
# ─────────────────────────────────────────────
@st.cache_resource
def get_client():
    api_key = st.secrets.get("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", ""))
    if not api_key or api_key == "填入你的阿里云Key":
        st.error("⚠️ 请在 .streamlit/secrets.toml 中填入 DASHSCOPE_API_KEY")
        st.stop()
    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

# ─────────────────────────────────────────────
# 病例知识库加载
# ─────────────────────────────────────────────
@st.cache_data
def load_cases():
    path = "data/cases/sample_cases.json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


# ─────────────────────────────────────────────
# RAG：语义检索相关病例
# ─────────────────────────────────────────────
def cosine_similarity(a: list, b: list) -> float:
    """纯Python余弦相似度（无需numpy）"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    return dot / (mag_a * mag_b) if mag_a * mag_b > 0 else 0.0


@st.cache_data(show_spinner=False)
def get_case_embeddings(_client, cases_json: str) -> list:
    """预计算所有病例的Embedding向量，启动后缓存"""
    cases = json.loads(cases_json)
    embeddings = []
    for case in cases:
        text = " ".join(filter(None, [
            case.get("diagnosis", ""),
            case.get("pain_type", ""),
            case.get("category", ""),
            case.get("risk_notes", "")
        ]))
        try:
            resp = _client.embeddings.create(
                model="text-embedding-v3",
                input=text,
                encoding_format="float"
            )
            embeddings.append(resp.data[0].embedding)
        except Exception:
            embeddings.append(None)
    return embeddings


def retrieve_similar_cases(client, query: str, cases: list, top_k: int = 3):
    """RAG检索：按语义相似度返回最相关的 top_k 个病例"""
    if not cases:
        return [], False
    cases_json = json.dumps(cases, ensure_ascii=False, sort_keys=True)
    case_embeddings = get_case_embeddings(client, cases_json)
    try:
        resp = client.embeddings.create(
            model="text-embedding-v3",
            input=query,
            encoding_format="float"
        )
        query_emb = resp.data[0].embedding
    except Exception:
        return cases[:top_k], False  # 降级：直接返回前N条
    scored = [
        (cosine_similarity(query_emb, emb), case)
        for emb, case in zip(case_embeddings, cases)
        if emb is not None
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]], True


# ─────────────────────────────────────────────
# ORT 评分计算
# ─────────────────────────────────────────────
def calc_ort(age, substance_history, psych_history, family_history):
    score = 0
    details = []
    try:
        age_int = int(age)
        if 16 <= age_int <= 45:
            score += 1
            details.append("年龄16-45岁 +1")
    except:
        pass
    sh = substance_history.lower()
    fh = family_history.lower()
    ph = psych_history.lower()
    if any(k in sh for k in ["酒", "饮酒", "alcohol"]):
        score += 3; details.append("本人饮酒史 +3")
    if any(k in sh for k in ["毒品", "大麻", "海洛因"]):
        score += 4; details.append("本人非法药物史 +4")
    if any(k in sh for k in ["处方药滥用"]):
        score += 5; details.append("本人处方药滥用 +5")
    if any(k in fh for k in ["酒", "饮酒"]):
        score += 1; details.append("家族饮酒史 +1")
    if any(k in fh for k in ["毒品", "大麻"]):
        score += 2; details.append("家族非法药物史 +2")
    if any(k in fh for k in ["处方"]):
        score += 4; details.append("家族处方药滥用史 +4")
    if any(k in ph for k in ["抑郁", "depression"]):
        score += 1; details.append("抑郁症史 +1")
    if any(k in ph for k in ["adhd", "多动"]):
        score += 2; details.append("ADHD史 +2")
    if any(k in ph for k in ["双相", "bipolar"]):
        score += 2; details.append("双相情感障碍史 +2")
    level = "🟢 低风险" if score <= 3 else ("🟡 中风险" if score <= 7 else "🔴 高风险")
    return score, level, details

# ─────────────────────────────────────────────
# Agent 调用（流式）
# ─────────────────────────────────────────────
def call_agent(client, system_prompt: str, user_prompt: str,
               model: str = "qwen-plus", placeholder=None) -> str:
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        max_tokens=2000,
        stream=True
    )
    result = ""
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            result += delta.content
            if placeholder:
                placeholder.markdown(result + "▌")
    if placeholder:
        placeholder.markdown(result)
    return result

# ─────────────────────────────────────────────
# 侧边栏导航
# ─────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/hospital.png", width=60)
    st.title("阿片类药物\n智能辅助系统")
    st.markdown("---")
    page = st.radio(
        "选择功能模块",
        ["🏥 临床咨询（医生端）", "🎓 医学生培训"],
        label_visibility="collapsed"
    )
    st.markdown("---")
    st.caption("⚠️ 本系统仅供参考，最终处方决策权归临床医生")
    st.caption("v1.0 | 通义千问驱动")

client = get_client()
cases = load_cases()

# ══════════════════════════════════════════════
# 模块一：临床咨询（医生端）
# ══════════════════════════════════════════════
if page == "🏥 临床咨询（医生端）":

    st.title("🏥 阿片类药物处方辅助决策")
    st.markdown("填写患者信息，系统将从**用药建议、证据溯源、风险评估**三个维度提供参考。")

    # ── 病例输入区 ──────────────────────────────
    with st.expander("📋 病例输入区", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            age   = st.number_input("年龄", 1, 120, 60)
            gender = st.selectbox("性别", ["男", "女"])
            pain_score = st.slider("疼痛评分 (NRS 0-10)", 0, 10, 7)
        with col2:
            diagnosis = st.text_input("主要诊断", placeholder="如：肺癌晚期骨转移")
            pain_type = st.selectbox("疼痛类型", ["癌性疼痛", "非癌性急性疼痛", "非癌性慢性疼痛"])
            department = st.selectbox("科室", ["肿瘤科", "骨科", "疼痛科", "急诊科", "口腔科", "其他"])
        with col3:
            current_meds   = st.text_area("当前用药", placeholder="每行一种，如：布洛芬400mg tid")
            comorbidities  = st.text_area("合并症", placeholder="如：高血压、糖尿病")

        col4, col5 = st.columns(2)
        with col4:
            substance_hist = st.text_input("本人物质滥用史", placeholder="如：大麻史，否则留空")
            psych_hist     = st.text_input("心理疾病史", placeholder="如：抑郁症，否则留空")
        with col5:
            family_hist    = st.text_input("家族物质滥用史", placeholder="如：父亲酗酒史，否则留空")
            extra_notes    = st.text_area("补充说明", placeholder="其他需要AI知道的信息")

    # ── ORT 评分展示 ──────────────────────────────
    ort_score, ort_level, ort_details = calc_ort(age, substance_hist, psych_hist, family_hist)

    ort_col1, ort_col2 = st.columns([1, 3])
    with ort_col1:
        st.metric("ORT 成瘾风险评分", f"{ort_score} 分", delta=ort_level)
    with ort_col2:
        if ort_details:
            st.info("风险因子：" + " | ".join(ort_details))
        else:
            st.success("无显著成瘾风险因子")

    # ── 生成按钮 ──────────────────────────────────
    if st.button("🚀 生成AI辅助建议", type="primary", use_container_width=True):
        if not diagnosis:
            st.warning("请填写主要诊断")
        else:
            # 构建病例摘要
            case_summary = f"""
患者信息：{age}岁{gender}，{diagnosis}，疼痛评分{pain_score}/10（{pain_type}）
科室：{department}
当前用药：{current_meds or '无'}
合并症：{comorbidities or '无'}
本人物质滥用史：{substance_hist or '无'}
心理疾病史：{psych_hist or '无'}
家族物质滥用史：{family_hist or '无'}
ORT成瘾风险评分：{ort_score}分（{ort_level}）
补充说明：{extra_notes or '无'}
"""
            # RAG 检索最相关病例
            rag_query = f"{diagnosis} {pain_type} {comorbidities or ''} {department}"
            similar_cases, rag_ok = retrieve_similar_cases(client, rag_query, cases, top_k=3)
            ref_cases_text = "\n".join([
                f"[{c['id']}] {c['diagnosis']} ({c.get('pain_type','')}) → {c['recommended_plan']}"
                for c in similar_cases
            ])

            # 显示RAG检索到的参考病例
            if similar_cases:
                rag_label = "🔍 RAG检索" if rag_ok else "📋 参考病例（关键词匹配）"
                with st.expander(f"{rag_label}：AI正在参考以下 {len(similar_cases)} 个相似病例", expanded=False):
                    for c in similar_cases:
                        st.markdown(f"- **[{c['id']}]** {c['diagnosis']} — {c.get('recommended_plan','')[:60]}...")

            tab1, tab2, tab3 = st.tabs(["💊 用药建议", "📚 证据溯源", "⚠️ 风险评估"])

            with tab1:
                st.markdown("#### AI 用药建议")
                ph1 = st.empty()
                call_agent(
                    client,
                    system_prompt="""你是阿片类药物处方辅助决策AI。
根据患者信息，给出：
1. 推荐处方方案（药物、剂量、给药途径、疗程）
2. WHO镇痛阶梯定位
3. 首选理由（2-3条）
4. 替代方案
格式清晰，使用Markdown，带可信度评分（如：建议可信度85%）""",
                    user_prompt=f"病例：\n{case_summary}\n\n参考相似病例：\n{ref_cases_text}",
                    model="qwen-max",
                    placeholder=ph1
                )

            with tab2:
                st.markdown("#### 证据溯源")
                ph2 = st.empty()
                call_agent(
                    client,
                    system_prompt="""你是医学文献溯源Agent。
根据病例，提供3-5条最相关循证证据：
- 证据等级（I/II/III/IV）
- 来源（期刊+年份）
- 核心结论
- 推荐强度
同时标注适用的指南条款（中国/美国）。""",
                    user_prompt=f"病例：\n{case_summary}",
                    model="qwen-plus",
                    placeholder=ph2
                )

            with tab3:
                st.markdown("#### 风险评估与政策合规")
                ph3 = st.empty()
                call_agent(
                    client,
                    system_prompt="""你是临床风险评估Agent。
请评估：
1. 主要临床风险（如呼吸抑制、便秘、过度镇静）
2. 药物相互作用警示
3. 中国政策合规提醒（麻醉药品处方规定、知情同意书要求）
4. 监测建议（随访频率、监测指标）
用⚠️标注高风险，用✅标注已满足要求。""",
                    user_prompt=f"病例：\n{case_summary}\nORT评分：{ort_score}（{ort_level}）",
                    model="qwen-plus",
                    placeholder=ph3
                )

    # ── 责任声明区 ────────────────────────────────
    st.markdown("---")
    st.info("📌 **责任声明**：本系统输出内容仅作为临床参考，不构成医嘱。最终处方决策权归主治医师，须结合具体临床情况判断。")


# ══════════════════════════════════════════════
# 模块二：医学生培训
# ══════════════════════════════════════════════
else:
    st.title("🎓 医学生处方培训系统")
    st.markdown("系统将生成**虚拟病例**供你练习，提交处方后获得**评估报告**与**个性化训练题**。")

    # 初始化 session state
    if "training_case" not in st.session_state:
        st.session_state.training_case = None
    if "evaluation_done" not in st.session_state:
        st.session_state.evaluation_done = False
    if "student_history" not in st.session_state:
        st.session_state.student_history = []
    if "next_case_ready" not in st.session_state:
        st.session_state.next_case_ready = False

    # ── 生成虚拟病例 ────────────────────────────────
    col_gen1, col_gen2, col_gen3 = st.columns(3)
    with col_gen1:
        difficulty = st.selectbox("难度", ["初级（癌性疼痛）", "中级（术后疼痛）", "高级（慢性疼痛+高风险因素）"])
    with col_gen2:
        dept_train = st.selectbox("科室场景", ["肿瘤科", "骨科", "疼痛科门诊", "急诊科"])
    with col_gen3:
        st.markdown("<br>", unsafe_allow_html=True)
        gen_btn = st.button("🎲 生成新病例", type="primary", use_container_width=True)

    if gen_btn:
        st.session_state.evaluation_done = False
        st.session_state.next_case_ready = False
        with st.spinner("正在生成虚拟病例..."):
            case_text = call_agent(
                client,
                system_prompt="""你是医学教育虚拟病例生成Agent。
生成一个用于阿片类药物处方培训的高拟真虚拟病例，格式如下：

【虚拟病例】
- 患者：[年龄]岁[性别]，[科室]
- 主诉：[症状描述，含疼痛评分NRS X/10]
- 诊断：[诊断名称]
- 既往史：[合并症、过敏史]
- 个人史：[物质使用史，可能有风险因素]
- 家族史：[可能有风险因素]
- 当前用药：[已用药物及效果]
- 检查结果：[简要辅助检查]
- 临床情境：[1-2句情境说明]

病例必须真实、具有教学价值，含适当的复杂性。""",
                user_prompt=f"生成{difficulty}难度的{dept_train}场景虚拟病例，用于阿片类药物处方培训。",
                model="qwen-max"
            )
            st.session_state.training_case = case_text
            st.session_state.evaluation_done = False

    # ── 展示病例 ────────────────────────────────────
    if st.session_state.training_case:
        st.markdown("---")
        with st.container(border=True):
            st.markdown("### 📋 虚拟病例")
            st.markdown(st.session_state.training_case)

        # ── 学生作答区 ──────────────────────────────
        if not st.session_state.evaluation_done:
            st.markdown("### ✍️ 你的处方方案")

            s_col1, s_col2 = st.columns(2)
            with s_col1:
                student_drug = st.text_input("药物名称与剂量", placeholder="如：盐酸吗啡缓释片 30mg")
                student_route = st.selectbox("给药途径", ["口服", "静脉", "肌肉注射", "皮下注射", "贴剂"])
                student_freq = st.text_input("给药频次", placeholder="如：q12h")
            with s_col2:
                student_duration = st.text_input("疗程", placeholder="如：2周，定期复诊")
                student_combo = st.text_area("联合用药/辅助措施", placeholder="如：止吐药、通便药、随访计划")
                student_reason = st.text_area("选择理由（选填）", placeholder="说明你的临床决策思路")

            if st.button("📤 提交方案，获取评估", type="primary", use_container_width=True):
                if not student_drug:
                    st.warning("请至少填写药物名称与剂量")
                else:
                    student_answer = f"""
处方方案：{student_drug} {student_route} {student_freq}
疗程：{student_duration}
联合用药：{student_combo}
决策理由：{student_reason}
"""
                    st.session_state.student_history.append({
                        "time": datetime.now().strftime("%H:%M"),
                        "case": st.session_state.training_case[:80] + "...",
                        "answer": student_answer[:100]
                    })

                    st.markdown("---")
                    st.markdown("### 📊 AI 评估报告")

                    e_tab1, e_tab2, e_tab3 = st.tabs(["📝 综合评分", "🔍 详细分析", "🎯 下一步训练"])

                    with e_tab1:
                        ph_eval = st.empty()
                        call_agent(
                            client,
                            system_prompt="""你是医学教育评估Agent，专注于阿片类药物处方培训。
评估学生的处方方案，输出格式：

## 综合评分
| 维度 | 得分 | 说明 |
|------|------|------|
| 药物选择 | X/25 | ... |
| 剂量合理性 | X/25 | ... |
| 风险评估 | X/25 | ... |
| 政策合规 | X/25 | ... |
**总分：XX/100**

## 亮点 ✅
- （列出1-3个做得好的地方）

## 需改进 ⚠️
- （列出1-3个需要改进的地方）

## 标准答案参考
（给出推荐方案及简短理由）""",
                            user_prompt=f"虚拟病例：\n{st.session_state.training_case}\n\n学生方案：\n{student_answer}",
                            model="qwen-max",
                            placeholder=ph_eval
                        )

                    with e_tab2:
                        ph_detail = st.empty()
                        call_agent(
                            client,
                            system_prompt="""你是医学教育分析Agent。
对学生处方进行深度分析：
1. WHO三阶梯定位是否正确？
2. 剂量是否符合指南（含老年人注意事项）？
3. ORT风险因素是否充分考虑？
4. 中国政策合规性（知情同意书、四专管理）？
5. 辅助治疗是否完整？
用引用具体指南条款支撑分析。""",
                            user_prompt=f"虚拟病例：\n{st.session_state.training_case}\n\n学生方案：\n{student_answer}",
                            model="qwen-plus",
                            placeholder=ph_detail
                        )

                    with e_tab3:
                        history_ctx = ""
                        if len(st.session_state.student_history) > 1:
                            history_ctx = "历史答题记录：\n" + "\n".join([
                                f"[{h['time']}] {h['answer']}"
                                for h in st.session_state.student_history[-3:]
                            ])

                        ph_next = st.empty()
                        call_agent(
                            client,
                            system_prompt="""你是个性化培训规划Agent。
根据学生本次及历史表现，给出：

## 学生能力画像
- 决策风格：（保守型/激进型/均衡型）
- 薄弱环节：（具体说明）

## 个性化训练建议
1. 下一步重点练习方向
2. 推荐学习资料（指南/文献）
3. 为该学生量身定制的下一个练习病例要点（告诉学生应该挑战什么场景）

## 一句话激励
（根据学生表现，给出鼓励或提醒）""",
                            user_prompt=f"本次病例：\n{st.session_state.training_case}\n\n学生方案：\n{student_answer}\n\n{history_ctx}",
                            model="qwen-max",
                            placeholder=ph_next
                        )

                    st.session_state.evaluation_done = True

    # ── 历史记录 ────────────────────────────────────
    if st.session_state.student_history:
        with st.expander(f"📈 答题历史（共 {len(st.session_state.student_history)} 次）"):
            for i, h in enumerate(reversed(st.session_state.student_history), 1):
                st.markdown(f"**{i}.** [{h['time']}] {h['case']}")
                st.caption(f"  → {h['answer']}")
