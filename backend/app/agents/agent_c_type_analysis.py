# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_c_distribution_model.py
# 功能：Agent C - 题型与难度分布建模
# ===========================================================

from collections import Counter, defaultdict
from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import save_question_bank, load_question_bank
from app.agents.models.quiz_models import QuestionBank

# -----------------------------------------------------------
# 工具函数：统计比例并格式化输出
# -----------------------------------------------------------

def _calc_distribution(counter: Counter):
    total = sum(counter.values())
    if total == 0:
        return {}
    return {k: round(v / total, 3) for k, v in counter.items()}


# -----------------------------------------------------------
# Agent C 主逻辑
# -----------------------------------------------------------

def run_agent_c(conversation_id: str):
    """
    Agent C：对题库进行统计建模，输出题型比例、难度权重和知识点覆盖分布。
    """
    print(f"🧩 [Agent C] 开始题型与难度分布建模...")

    # 1️⃣ 获取题库
    qb: QuestionBank = shared_state.question_bank
    if qb is None or not qb.questions:
        print("⚠️ shared_state.question_bank 为空，尝试从磁盘加载。")
        qb = load_question_bank(conversation_id)

    if qb is None or not qb.questions:
        print("❌ 无可分析题库，Agent C 终止。")
        return None

    print(f"👉 已加载题库，共 {len(qb.questions)} 题。")

    # 2️⃣ 统计各分布
    type_counter = Counter()
    difficulty_counter = Counter()
    knowledge_counter = Counter()

    for q in qb.questions:
        type_counter[q.question_type or "未知类型"] += 1
        difficulty_counter[q.difficulty or "medium"] += 1
        for kp in q.knowledge_points or ["通用知识"]:
            knowledge_counter[kp] += 1

    # 3️⃣ 生成比例分布
    type_dist = _calc_distribution(type_counter)
    diff_dist = _calc_distribution(difficulty_counter)
    kp_dist = _calc_distribution(knowledge_counter)

    # 4️⃣ 构建统计模板对象
    distribution_model = {
        "conversation_id": conversation_id,
        "total_questions": len(qb.questions),
        "type_distribution": type_dist,
        "difficulty_distribution": diff_dist,
        "knowledge_point_distribution": kp_dist
    }

    # 存入共享状态
    shared_state.distribution_model = distribution_model

    # 5️⃣ 输出统计信息
    print("\n📊 题型比例：")
    for t, v in type_dist.items():
        print(f"  - {t}: {v*100:.1f}%")

    print("\n📊 难度分布：")
    for d, v in diff_dist.items():
        print(f"  - {d}: {v*100:.1f}%")

    print("\n📊 知识点覆盖：")
    for kp, v in kp_dist.items():
        print(f"  - {kp}: {v*100:.1f}%")

    print(f"\n✅ 题型与难度分布建模完成，模型已存入 shared_state。")
    return distribution_model
