# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_d_sample_parser.py
# 功能：Agent D - 样例试卷结构解析（支持容错与 Agent C 回退）
# ===========================================================

import os
import re
from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import load_question_bank
from app.agents.models.quiz_models import QuestionBank


# -----------------------------------------------------------
# 正则模式（章节 / 题号区间 / 分值）
# -----------------------------------------------------------

SECTION_PATTERN = re.compile(r"(第[一二三四五六七八九十]+部分|Section\s+\d+|Part\s+\d+)", re.IGNORECASE)
QUESTION_RANGE_PATTERN = re.compile(r"(\d+)[\-~–—](\d+)\s*题?")
SCORE_PATTERN = re.compile(r"(\d+)\s*分")


# -----------------------------------------------------------
# 改进版结构提取
# -----------------------------------------------------------

def parse_exam_structure_from_text(text: str):
    """
    支持两类格式：
    1. 第X部分 ... （1-10题，每题2分）
    2. 普通题型标题（选择题 / 简答题 / 编程题）
    """
    sections = []
    current_section = None
    lines = text.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # ✅ 检测章节标题
        if SECTION_PATTERN.search(line) or any(k in line for k in ["选择题", "简答题", "编程题", "判断题"]):
            if current_section:
                sections.append(current_section)
            current_section = {"title": line, "question_ranges": [], "score": None}
            continue

        # ✅ 匹配题号区间或单题号
        match_range = QUESTION_RANGE_PATTERN.search(line)
        if match_range:
            q_from, q_to = match_range.groups()
            if current_section is None:
                current_section = {"title": "未知部分", "question_ranges": [], "score": None}
            current_section["question_ranges"].append({"from": int(q_from), "to": int(q_to)})
        elif re.match(r"^\d+\.", line):
            q_num = int(line.split(".")[0])
            if current_section is None:
                current_section = {"title": "未知部分", "question_ranges": [], "score": None}
            current_section["question_ranges"].append({"from": q_num, "to": q_num})

        # ✅ 匹配分值
        match_score = SCORE_PATTERN.search(line)
        if match_score:
            if current_section is None:
                current_section = {"title": "未知部分", "question_ranges": [], "score": None}
            current_section["score"] = int(match_score.group(1))

    if current_section:
        sections.append(current_section)

    return sections


# -----------------------------------------------------------
# 主函数：Agent D
# -----------------------------------------------------------

def run_agent_d(conversation_id: str, file_path: str = None):
    print("🧩 [Agent D] 开始样例试卷结构解析...")

    # 1️⃣ 尝试读取文本
    text = None
    if file_path and os.path.exists(file_path):
        ext = os.path.splitext(file_path)[-1].lower()
        try:
            if ext == ".txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            elif ext in [".pdf", ".docx", ".pptx"]:
                qb = shared_state.question_bank or load_question_bank(conversation_id)
                if qb and len(qb.questions) > 0:
                    text = "\n".join([q.stem for q in qb.questions])
        except Exception as e:
            print(f"[⚠️ 文件读取失败] {e}")

    if not text:
        print("⚠️ 无法读取样例文本，将尝试从 Agent C 模板构建默认结构。")

    # 2️⃣ 结构解析
    sections = parse_exam_structure_from_text(text) if text else []

    # 3️⃣ 回退逻辑：如果解析失败 → 用 Agent C 的分布信息生成默认模板
    if not sections:
        print("⚠️ 未识别到有效章节结构，使用 Agent C 的分布信息生成通用模板。")

        dist_model = getattr(shared_state, "distribution_model", None)
        if dist_model:
            type_dist = dist_model.get("type_distribution", {})
            sections = []
            q_start = 1
            total_questions = dist_model.get("total_questions", 10)

            for t, ratio in type_dist.items():
                count = max(1, int(total_questions * ratio))
                q_end = q_start + count - 1
                sections.append({
                    "title": f"{t}区",
                    "question_ranges": [{"from": q_start, "to": q_end}],
                    "score": None
                })
                q_start = q_end + 1

        # 若 Agent C 也无分布信息，则使用静态模板
        if not sections:
            print("⚠️ 无 Agent C 模板信息，使用静态默认模板。")
            sections = [
                {"title": "选择题", "question_ranges": [{"from": 1, "to": 10}], "score": 2},
                {"title": "简答题", "question_ranges": [{"from": 11, "to": 15}], "score": 6},
                {"title": "编程题", "question_ranges": [{"from": 16, "to": 18}], "score": 10},
            ]

    # 4️⃣ 写入共享状态
    structure_template = {
        "conversation_id": conversation_id,
        "section_count": len(sections),
        "sections": sections
    }
    shared_state.sample_structure = structure_template

    print(f"✅ Agent D 结构生成完成，共 {len(sections)} 个部分。")
    for s in sections:
        print(f"📘 {s['title']} → {s.get('question_ranges', [])} | 分值: {s.get('score')}")

    return structure_template
