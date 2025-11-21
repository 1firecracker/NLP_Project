# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_e_question_generation.py
# 功能：Agent E – 智能出题生成（高保真仿真版，最小差异修正版）
# ===========================================================

import os
import json
import re
import aiohttp
import asyncio
from dotenv import load_dotenv
from app.agents.shared_state import shared_state
from app.agents.models.quiz_models import Question, QuestionBank
from app.agents.database.question_bank_storage import save_question_bank

# -----------------------------------------------------------
# 环境配置
# -----------------------------------------------------------

load_dotenv()
API_URL = os.getenv("LLM_BINDING_HOST", "https://api.siliconflow.cn/v1")
API_KEY = os.getenv("LLM_BINDING_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def _has_cjk(s: str) -> bool:
    import re
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))

def _detect_language_from_stem(stem: str) -> str:
    return "Chinese" if _has_cjk(stem or "") else "English"

def _extract_json_array(text: str):
    # 标准 JSON 数组
    m = re.search(r"\[\s*(?:\{.*?\}\s*,\s*)*\{.*?\}\s*\]", text, re.S)
    if m:
        return json.loads(m.group(0))
    # 代码块 ```json ... ```
    m = re.search(r"```(?:json)?\s*(\[\s*.*?\s*\])\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    # 全角括号 → 半角再匹配
    txt2 = text.replace("【", "[").replace("】", "]")
    m = re.search(r"\[\s*(?:\{.*?\}\s*,\s*)*\{.*?\}\s*\]", txt2, re.S)
    if m:
        return json.loads(m.group(0))
    # 单对象（极少数模型直接给一题）
    m = re.search(r"\{\s*.*?\s*\}", text, re.S)
    if m:
        try:
            return [json.loads(m.group(0))]
        except:
            pass
    return []

# -----------------------------------------------------------
# Prompt 构造
# -----------------------------------------------------------

def build_prompt(section, distribution_model, examples=None, global_difficulty="medium",
                 expected_count=None, expected_type=None, expected_kps=None,
                 target_difficulty_hint="保持与样例相同层级，但在深度与综合性上提高",
                 min_subparts=2,expected_language=None):
    """
    构造高保真出题 Prompt：
    - 题量/题型硬约束
    - 知识点必含清单
    - 深度要求（多步子问、定量分析、边界/对比）
    """
    type_info = distribution_model.get("type_distribution", {})
    diff_info = distribution_model.get("difficulty_distribution", {})
    kp_info   = distribution_model.get("knowledge_point_distribution", {})

    prompt = f"""
你是一名经验丰富的命题专家。请根据以下约束生成新的高质量题目：
1️⃣ 难度与样题一致（{target_difficulty_hint}），不得简化题意、缩短篇幅或降低逻辑复杂度；
2️⃣ 确保知识点覆盖合理，符合专业课程考试风格；
3️⃣ 输出格式必须为 JSON 数组，不含额外文字。

【出题目标】
- 当前章节：{section['title']}
- 建议难度水平：{global_difficulty}
- 题型分布参考：{json.dumps(type_info, ensure_ascii=False, indent=2)}
- 难度分布参考：{json.dumps(diff_info, ensure_ascii=False, indent=2)}
- 知识点覆盖参考：{json.dumps(kp_info, ensure_ascii=False, indent=2)}
"""
    if expected_count is not None:
        prompt += f"\n【数量约束】本节必须严格生成 {expected_count} 道题（不多不少）。"
    if expected_type:
        prompt += f"\n【题型约束】本节题型固定为：{expected_type}（每题 question_type 保持一致）。"
    if expected_kps:
        prompt += f"\n【知识点约束】本节生成的题目必须显式覆盖以下知识点：{expected_kps}。"

    # —— 深度与结构要求（关键）——
    prompt += f"""
【深度与结构要求】
- 题干需包含至少 {min_subparts} 个有递进关系的子问（(a)(b)(c) …），覆盖不同角度（定义/推导/比较/反例/复杂度/工程取舍）。
- 至少包含一次“定量计算或公式推导”与一次“方法对比或边界/异常情形分析”。
- 如为综合/应用类题，要求设置真实数据片段或近似数据、并给出明确计算或判断步骤。
- 对于选择题，干扰项必须基于常见误区（不要明显错误的选项）。

【样题参考】
"""
    if examples:
        example_snippets = []
        for q in examples[:3]:
            snippet = (
                f"题干：{q.stem}\n"
                f"答案：{q.answer or '（无答案）'}\n"
                f"知识点：{', '.join(q.knowledge_points)}\n"
                f"难度：{q.difficulty}\n"
                f"题型：{q.question_type}\n"
            )
            example_snippets.append(snippet)
        prompt += "\n---\n".join(example_snippets)

    # ✅ 在这里插入语言约束逻辑
    if expected_language:
        prompt += f"\n【语言约束】题干（stem）、答案（answer）、解析（explanation）必须使用 {expected_language} 输出；" \
                  f"knowledge_points 字段可以使用中文。"

    prompt += """
【输出格式示例】
[
  {
    "stem": "题干文本……（包含(a)(b)(c)等子问）",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "正确答案或要点（选择题写选项字母；简答/综合题给出关键步骤与结论，不需要长篇推理）",
    "explanation": "简要说明正确原因、关键计算/判断边界，避免长篇推理文字",
    "difficulty": "easy | medium | hard",
    "knowledge_points": ["涉及的知识点 1", "知识点 2", "…"],
    "question_type": "single_choice | short_answer | programming | 算法应用题 | 综合分析题 | 简答题"
  }
]
只输出 JSON，不要添加解释或其他自然语言。
"""
    return prompt



# -----------------------------------------------------------
# 调用 LLM 异步生成
# -----------------------------------------------------------

async def async_generate_section(session, section, distribution_model, examples=None, global_difficulty="medium"):
    # 期望题数
    expected_count = None
    try:
        ranges = section.get("question_ranges", [])
        expected_count = sum(r.get("to", 0) - r.get("from", 0) + 1 for r in ranges if r)
    except Exception:
        pass

    # 期望题型（来自标题 “… Section”）
    expected_type = None
    title = section.get("title") or ""
    if isinstance(title, str) and title.endswith(" Section"):
        expected_type = title[:-8]

    # 模板知识点与难度提示（在 run_agent_e 里设置进 section）
    expected_kps = section.get("expected_kps")
    target_difficulty_hint = section.get("target_difficulty_hint", "保持与样例相同层级，但在深度与综合性上提高")

    # 🆕 根据 question_ranges 选择对应的 examples
    section_examples = examples  # 默认使用全部 examples
    if examples and len(examples) > 0:
        try:
            ranges = section.get("question_ranges", [])
            if ranges and len(ranges) > 0:
                # 获取第一个 range 的起始位置（1-based index）
                start_idx = ranges[0].get("from", 1) - 1  # 转换为 0-based
                end_idx = ranges[0].get("to", 1)  # inclusive
                section_examples = examples[start_idx:end_idx]
                print(f"[📌 Section] 使用 examples[{start_idx}:{end_idx}]，共 {len(section_examples)} 道题")
        except Exception as e:
            print(f"[⚠️ 选择 section examples 失败] {e}")

    prompt = build_prompt(
        section, distribution_model, section_examples, global_difficulty,
        expected_count=expected_count, expected_type=expected_type,
        expected_kps=expected_kps, target_difficulty_hint=target_difficulty_hint,
        min_subparts=2, expected_language=section.get("expected_language")
    )

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一名高级考试命题专家，擅长生成尺度恰当且覆盖全面的深度试题。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 3200,   # ↑ 略增
        "temperature": 0.6,   # ↓ 略降，提升稳定度与对齐度
        "top_p": 0.95,
    }

    try:
        async with session.post(f"{API_URL}/chat/completions", headers=HEADERS, json=payload, timeout=240) as resp:
            res = await resp.json()
            content = res["choices"][0]["message"]["content"]
            items = _extract_json_array(content)

            # 超额裁剪（不足不做二次重试，保持最小改动策略）
            if expected_count is not None and len(items) > expected_count:
                items = items[:expected_count]
            return items
    except Exception as e:
        print(f"[❌ LLM 生成失败] section={section.get('title', 'unknown')}, error={e}")
        print(f"[🔄 使用降级方案] 基于当前 section 的样例题目生成")
        
        # 降级方案：使用样例题目或生成简单题目
        fallback_questions = []
        
        # 🆕 使用 section_examples 而不是 examples（确保每个 section 用不同的题目）
        if section_examples and len(section_examples) > 0:
            for idx, example in enumerate(section_examples[:expected_count or 1], 1):
                q_dict = example.dict() if hasattr(example, 'dict') else example
                fallback_questions.append({
                    "stem": q_dict.get('stem', f"示例题目 {idx}"),
                    "options": q_dict.get('options', []),
                    "answer": q_dict.get('answer', '参考答案'),
                    "explanation": q_dict.get('explanation', '详见教材'),
                    "difficulty": global_difficulty,
                    "knowledge_points": q_dict.get('knowledge_points', ['通用知识']),
                    "question_type": q_dict.get('question_type', 'short_answer')
                })
        else:
            # 生成默认题目
            for i in range(expected_count or 3):
                fallback_questions.append({
                    "stem": f"请简述{section.get('name', '相关')}的主要概念。",
                    "options": [],
                    "answer": "请参考教材相关章节。",
                    "explanation": "本题考查基础概念理解。",
                    "difficulty": global_difficulty,
                    "knowledge_points": [section.get('name', '通用知识')],
                    "question_type": "short_answer"
                })
        
        print(f"[✅ 降级方案生成] {len(fallback_questions)} 道题目")
        return fallback_questions



# -----------------------------------------------------------
# 主函数
# -----------------------------------------------------------

def run_agent_e(conversation_id: str):
    print("🧩 [Agent E] 高保真智能出题生成开始...")

    qb = shared_state.question_bank
    dist_model = shared_state.distribution_model
    structure_model = getattr(shared_state, "sample_structure", None)

    if not dist_model:
        print("⚠️ 缺少 Agent C 输出，无法生成分布模型。")
        return None

    # —— 若存在模板题库：逐题建段（顺序对齐 + 题型对齐 + 知识点对齐）——
    if qb and getattr(qb, "questions", None):
        sections = []
        TYPE_TITLE_EN = {
            "简答题": "Short Answer",
            "综合题": "Comprehensive",
            "综合分析题": "Comprehensive",
            "算法应用题": "Applied Algorithms",
            "计算题": "Problem Solving",
        }
        for idx, tq in enumerate(qb.questions, start=1):
            t = (tq.question_type or "short_answer")
            # 标题英文化，避免中英混排干扰模型语言选择
            title_en = TYPE_TITLE_EN.get(t, t if _has_cjk(t) is False else "Section")
            expected_language = _detect_language_from_stem(getattr(tq, "stem", "") or "")
            sections.append({
                "title": f"{title_en} Section",
                "question_ranges": [{"from": idx, "to": idx}],
                "score": None,
                "expected_kps": tq.knowledge_points if getattr(tq, "knowledge_points", None) else None,
                "target_difficulty_hint": "保持与样例相同层级，但在深度与综合性上提高",
                "expected_language": expected_language,  # ← 新增：每题的期望语种
            })
        structure_model = {"sections": sections}
    else:
        # 无模板则保留你的原兜底，顺便修补“sections 为空也视为无效结构”
        if (not structure_model
            or structure_model.get("section_count", 0) == 0
            or not structure_model.get("sections")):
            print("⚠️ 无有效样例结构，使用 Agent C 的题型比例生成虚拟章节。")
            type_dist = dist_model.get("type_distribution", {})
            sections = []
            q_start = 1
            total_questions = dist_model.get("total_questions", 10)
            for t, ratio in type_dist.items():
                count = max(1, int(total_questions * ratio))
                q_end = q_start + count - 1
                sections.append({
                    "title": f"{t} Section",
                    "question_ranges": [{"from": q_start, "to": q_end}],
                    "score": None
                })
                q_start = q_end + 1
            structure_model = {"sections": sections}

    # 自动检测全局难度（保持不变）
    if qb and getattr(qb, "questions", None):
        difficulties = [q.difficulty for q in qb.questions if q.difficulty]
        global_difficulty = max(set(difficulties), key=difficulties.count) if difficulties else "medium"
    else:
        global_difficulty = "medium"

    print(f"👉 检测到整体难度：{global_difficulty}")

    async def main():
        async with aiohttp.ClientSession() as session:
            tasks = [
                async_generate_section(session, section, dist_model, qb.questions if qb else None, global_difficulty)
                for section in structure_model["sections"]
            ]
            return await asyncio.gather(*tasks)

    all_sections = asyncio.run(main())

    # 合并生成题目（保持不变）
    generated_questions = []
    for sec in all_sections:
        for item in sec:
            try:
                q = Question(
                    id=f"GEN_{len(generated_questions)+1:03d}",
                    stem=item.get("stem"),
                    options=item.get("options", []),
                    answer=item.get("answer"),
                    explanation=item.get("explanation"),
                    difficulty=item.get("difficulty", "medium"),
                    knowledge_points=item.get("knowledge_points", ["通用知识"]),
                    question_type=item.get("question_type", "short_answer")
                )
                generated_questions.append(q)
            except Exception as e:
                print(f"[⚠️ 题目解析异常] {e}")

    new_qb = QuestionBank(questions=generated_questions)
    shared_state.generated_exam = new_qb

    save_path = save_question_bank(f"{conversation_id}_generated", new_qb)
    print(f"✅ 高保真 Agent E 完成，共生成 {len(generated_questions)} 题。")
    print(f"💾 题库保存路径：{save_path}")
    return new_qb



