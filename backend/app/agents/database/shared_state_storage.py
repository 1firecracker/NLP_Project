# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/database/shared_state_storage.py
# 功能：共享状态（SharedState）的持久化与加载
# 说明：
#   - 每个 conversation_id 对应一个独立目录
#   - 文件结构：
#       data/<conversation_id>/quiz/shared_state.json
#   - 主要用途：
#       * 保存多 Agent 出题流程中的中间结果
#       * 支持系统重启后恢复会话状态
# ===========================================================

import os
import json
from typing import Optional
from app.agents.shared_state import SharedState
from datetime import datetime


# -----------------------------------------------------------
# 配置
# -----------------------------------------------------------

# 基础保存目录（可根据项目需要改为绝对路径）
BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "../../../data")

# 规范化路径
BASE_DATA_DIR = os.path.abspath(BASE_DATA_DIR)


# -----------------------------------------------------------
# 工具函数
# -----------------------------------------------------------

def _ensure_dir(path: str):
    """确保目标目录存在"""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def _get_state_file_path(conversation_id: str) -> str:
    """返回指定会话的状态文件路径"""
    folder = os.path.join(BASE_DATA_DIR, conversation_id, "quiz")
    _ensure_dir(folder)
    return os.path.join(folder, "shared_state.json")


# -----------------------------------------------------------
# 核心函数
# -----------------------------------------------------------

def save_state(conversation_id: str, state: SharedState) -> str:
    """
    保存当前共享状态到磁盘
    Args:
        conversation_id: 会话ID（一般由前端或API自动生成）
        state: SharedState 实例
    Returns:
        保存的文件路径
    """
    file_path = _get_state_file_path(conversation_id)

    data = {
        "conversation_id": conversation_id,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "state": state.snapshot()
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return file_path


def load_state(conversation_id: str) -> Optional[SharedState]:
    """
    从磁盘加载指定会话的共享状态
    Args:
        conversation_id: 会话ID
    Returns:
        SharedState 实例或 None
    """
    file_path = _get_state_file_path(conversation_id)
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    state_data = raw.get("state", {})

    # 初始化 SharedState
    state = SharedState()

    # 逐字段赋值（防止字段缺失时报错）
    from app.agents.models.quiz_models import (
        QuestionBank, KnowledgePointStats, QuestionTypeStats,
        SampleExam, GeneratedQuestions, ExamPaper, QualityReport
    )

    try:
        if state_data.get("question_bank"):
            state.question_bank = QuestionBank(**state_data["question_bank"])
        if state_data.get("knowledge_point_stats"):
            state.knowledge_point_stats = KnowledgePointStats(**state_data["knowledge_point_stats"])
        if state_data.get("question_type_stats"):
            state.question_type_stats = QuestionTypeStats(**state_data["question_type_stats"])
        if state_data.get("sample_exam_stats"):
            state.sample_exam_stats = SampleExam(**state_data["sample_exam_stats"])
        if state_data.get("generated_questions"):
            state.generated_questions = GeneratedQuestions(**state_data["generated_questions"])
        if state_data.get("exam_paper"):
            state.exam_paper = ExamPaper(**state_data["exam_paper"])
        if state_data.get("quality_report"):
            state.quality_report = QualityReport(**state_data["quality_report"])
    except Exception as e:
        print(f"[⚠️ Warning] Failed to parse some fields from saved state: {e}")

    return state


def delete_state(conversation_id: str) -> bool:
    """
    删除指定会话的状态文件
    Returns:
        True / False
    """
    file_path = _get_state_file_path(conversation_id)
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False


def list_saved_conversations() -> list:
    """
    列出当前已保存的 conversation_id 列表
    """
    if not os.path.exists(BASE_DATA_DIR):
        return []
    return [
        d for d in os.listdir(BASE_DATA_DIR)
        if os.path.isdir(os.path.join(BASE_DATA_DIR, d))
    ]
