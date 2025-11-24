# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/quiz_graph.py
# 功能：Agent 依赖图与流水线调度器
# ===========================================================

import os
from datetime import datetime
from app.agents.agent_a_data_preparation import run_agent_a
from app.agents.agent_b_knowledge_analysis import run_agent_b
from app.agents.agent_c_type_analysis import run_agent_c
from app.agents.agent_e_question_generation import run_agent_e
from app.agents.agent_f_quality_control import run_agent_f
from app.agents.agent_g_grader import run_agent_g
from app.agents.agent_h_learning_advisor import run_agent_h
from app.agents.shared_state import shared_state

# ===========================================================
# Agent 调度图定义
# ===========================================================
class AgentGraph:
    """
    定义题目生成系统中各 Agent 的依赖图。
    注：G（评分）和 H（学习建议）是运行时根据学生提交触发，不在主流水线中。
    """
    def __init__(self):
        self.nodes = ["A", "B", "C", "E", "F", "G", "H"]
        self.edges = {
            "A": [],
            "B": ["A"],
            "C": ["A", "B"],
            "E": ["A", "B", "C"],
            "F": ["E"],
            "G": ["E"],  # G 依赖生成题库
            "H": ["G"],  # H 依赖评分结果
        }

    def get_dependencies(self, agent):
        """返回指定 Agent 的所有依赖节点"""
        return self.edges.get(agent, [])

    def get_order(self, up_to="F"):
        """返回执行顺序（A→up_to）"""
        idx = self.nodes.index(up_to)
        return self.nodes[: idx + 1]

# ===========================================================
# Agent 链式执行
# ===========================================================
def run_agent_chain(conversation_id: str,
                    sample_files=None,
                    up_to="E",
                    expected_language="English"):
    """
    统一执行出题流水线。
    - up_to: 可为 "A"~"F"，决定执行到哪个 Agent。
    - 自动根据依赖顺序执行前序 Agent。
    """

    graph = AgentGraph()
    exec_order = graph.get_order(up_to)

    print(f"🧠 [Pipeline] 开始执行 Agent 链：{' → '.join(exec_order)}")
    print(f"📁 Conversation ID: {conversation_id}")
    print("==========================================================")

    results = {}

    # A: 数据准备
    if "A" in exec_order:
        results["A"] = run_agent_a(conversation_id, sample_files or [])
        print("✅ Agent A 完成\n")

    # B: 知识点分析
    if "B" in exec_order:
        results["B"] = run_agent_b(conversation_id)
        print("✅ Agent B 完成\n")

    # C: 题型/难度建模
    if "C" in exec_order:
        results["C"] = run_agent_c(conversation_id)
        print("✅ Agent C 完成\n")

    # E: 智能出题生成
    if "E" in exec_order:
        results["E"] = run_agent_e(conversation_id)
        print("✅ Agent E 完成\n")

    # F: 质量控制（语言统一 + 覆盖率 + 重复度）
    if "F" in exec_order:
        results["F"] = run_agent_f(conversation_id, expected_language=expected_language)
        print("✅ Agent F 完成\n")

    print("==========================================================")
    print(f"🎯 Pipeline 执行完成，阶段：{exec_order[-1]}")
    print(f"📅 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return results


# ===========================================================
# 健康检查与调试
# ===========================================================
def validate_outputs(conversation_id: str):
    """
    用“能否加载成功”作为存在性判定，避免相对/绝对路径差异导致的误报。
    """
    from app.agents.database.question_bank_storage import load_question_bank
    checks = {}

    # A/B：同一份题库文件（Agent B会回写到同路径）
    qb_ab = load_question_bank(conversation_id)
    checks["A"] = qb_ab is not None
    checks["B"] = qb_ab is not None

    # C：分布模型是否在内存
    checks["C"] = hasattr(shared_state, "distribution_model") and bool(shared_state.distribution_model)

    # E：生成题库是否能从磁盘加载
    qb_e = load_question_bank(f"{conversation_id}_generated")
    checks["E"] = qb_e is not None

    # F：校对后题库是否能从磁盘加载
    qb_f = load_question_bank(f"{conversation_id}_corrected")
    checks["F"] = qb_f is not None

    # G：评分题库是否能从磁盘加载（学生提交后生成）
    qb_g = load_question_bank(f"{conversation_id}_graded")
    checks["G"] = qb_g is not None

    # H：学习建议是否存在（检查文件夹）
    import os
    from app.agents.database.question_bank_storage import BASE_DATA_DIR
    advisor_dir = os.path.join(BASE_DATA_DIR, conversation_id, "learning_advice")
    checks["H"] = os.path.exists(advisor_dir) and len(os.listdir(advisor_dir) if os.path.isdir(advisor_dir) else []) > 0

    print("\n🧾 [Pipeline Health Check]")
    for agent, ok in checks.items():
        status = "✅ OK" if ok else "❌ Missing"
        print(f"  - Agent {agent}: {status}")
    return checks
# ===========================================================
# 调试入口
# ===========================================================
if __name__ == "__main__":
    # 示例：执行到 E
    run_agent_chain("test_a_text", [r"D:\NLP_Project\text.txt"], up_to="F")
    validate_outputs("test_a_text")
