# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/database/question_bank_storage.py
# 功能：题库（QuestionBank）的独立存取
# 说明：
#   - 每个 conversation_id 对应一个专属题库文件：
#       data/<conversation_id>/quiz/question_bank.json
#   - 可被 Agent A（生成题库） 和 Agent E（读取题库） 共同使用
# ===========================================================

import os
import json
from typing import Optional
from datetime import datetime
from app.agents.models.quiz_models import QuestionBank

# -----------------------------------------------------------
# 基础路径配置
# -----------------------------------------------------------

BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "../../../data")
BASE_DATA_DIR = os.path.abspath(BASE_DATA_DIR)

# -----------------------------------------------------------
# 工具函数
# -----------------------------------------------------------

def _ensure_dir(path: str):
    """确保路径存在"""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def _get_bank_file_path(conversation_id: str) -> str:
    """获取题库文件路径"""
    folder = os.path.join(BASE_DATA_DIR, conversation_id, "quiz")
    _ensure_dir(folder)
    return os.path.join(folder, "question_bank.json")

# -----------------------------------------------------------
# 主函数
# -----------------------------------------------------------

def save_question_bank(conversation_id: str, question_bank: QuestionBank) -> str:
    """
    保存题库到磁盘
    Args:
        conversation_id: 会话ID
        question_bank: QuestionBank 对象
    Returns:
        保存文件路径
    """
    file_path = _get_bank_file_path(conversation_id)
    data = {
        "conversation_id": conversation_id,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question_count": len(question_bank.questions),
        "question_bank": question_bank.model_dump()
    }

    # 保存 JSON 文件
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 额外生成 TXT 格式的答案文件（方便学生参考格式）
    try:
        txt_file_path = file_path.replace("question_bank.json", "standard_answers.txt")
        with open(txt_file_path, "w", encoding="utf-8") as f:
            f.write("# 标准答案参考文件\n")
            f.write(f"# 会话ID: {conversation_id}\n")
            f.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 题目总数: {len(question_bank.questions)}\n")
            f.write("#" + "="*60 + "\n")
            f.write("# 说明：此文件包含所有题目的标准答案，供参考\n")
            f.write("# 学生提交答案时可参考此格式\n")
            f.write("#" + "="*60 + "\n\n")
            
            for idx, question in enumerate(question_bank.questions, 1):
                # 获取题目ID和答案
                q_id = question.id if hasattr(question, 'id') else (question.get('id') if isinstance(question, dict) else f"Q{idx:03d}")
                answer = question.answer if hasattr(question, 'answer') else (question.get('answer') if isinstance(question, dict) else "")
                
                # 格式1: 数字序号，每题后添加分隔符
                f.write(f"{idx}. {answer}\n")
                f.write("---END_OF_ANSWER---\n\n")  # 分隔符，用于区分多行答案
            
            # 追加其他格式示例
            f.write("\n" + "="*60 + "\n")
            f.write("# 其他支持的格式（任选其一）：\n")
            f.write("="*60 + "\n\n")
            
            f.write("# 格式A - 使用题目ID:\n")
            for idx, question in enumerate(question_bank.questions[:3], 1):  # 只显示前3题示例
                q_id = question.id if hasattr(question, 'id') else (question.get('id') if isinstance(question, dict) else f"GEN_{idx:03d}")
                answer = question.answer if hasattr(question, 'answer') else (question.get('answer') if isinstance(question, dict) else "")
                f.write(f"{q_id}: {answer[:100]}...\n")
            f.write("...\n\n")
            
            f.write("# 格式B - 使用Q编号:\n")
            for idx in range(1, min(4, len(question_bank.questions) + 1)):  # 前3题示例
                answer = question_bank.questions[idx-1].answer if hasattr(question_bank.questions[idx-1], 'answer') else ""
                f.write(f"Q{idx:03d}: {answer[:100]}...\n")
            f.write("...\n\n")
        
        print(f"✅ 已生成标准答案TXT文件: {txt_file_path}")
    except Exception as e:
        print(f"⚠️ 生成TXT答案文件失败: {e}")

    return file_path



def load_question_bank(conversation_id: str) -> Optional[QuestionBank]:
    """
    从磁盘加载题库
    Args:
        conversation_id: 会话ID
    Returns:
        QuestionBank 实例或 None
    """
    file_path = _get_bank_file_path(conversation_id)
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    qb_data = raw.get("question_bank")
    if not qb_data:
        return None

    try:
        return QuestionBank(**qb_data)
    except Exception as e:
        print(f"[⚠️ Warning] Failed to load QuestionBank: {e}")
        return None


def list_question_banks() -> list:
    """
    列出当前 data/ 下所有已保存题库
    Returns:
        [{'conversation_id': str, 'question_count': int, 'saved_at': str}, ...]
    """
    if not os.path.exists(BASE_DATA_DIR):
        return []

    results = []
    for cid in os.listdir(BASE_DATA_DIR):
        folder = os.path.join(BASE_DATA_DIR, cid, "quiz")
        file_path = os.path.join(folder, "question_bank.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "conversation_id": cid,
                    "question_count": data.get("question_count", 0),
                    "saved_at": data.get("saved_at", "unknown")
                })
            except Exception:
                continue

    return results


def delete_question_bank(conversation_id: str) -> bool:
    """
    删除指定会话的题库文件
    Returns:
        True / False
    """
    file_path = _get_bank_file_path(conversation_id)
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False


def find_saved_question_bank_path(conversation_id: str) -> str | None:
    """返回已保存题库文件的绝对路径（存在则返回路径，否则返回 None）"""
    file_path = _get_bank_file_path(conversation_id)
    return file_path if os.path.exists(file_path) else None
