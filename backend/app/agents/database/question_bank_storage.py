# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/database/question_bank_storage.py
# 功能：题库（QuestionBank）的独立存取
# 说明：
#   - 每个 conversation_id 对应一个专属题库目录：
#       data/<conversation_id>/quiz/question_bank.json
#       data/<conversation_id>/generated/question_bank.json
#       data/<conversation_id>/corrected/question_bank.json
#       data/<conversation_id>/graded/question_bank.json
#   - 可被 Agent A（生成题库） 和 Agent E/F/G（读取题库） 共同使用
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
VARIANT_SUFFIXES = ["generated", "corrected", "graded"]

# -----------------------------------------------------------
# 工具函数
# -----------------------------------------------------------

def _ensure_dir(path: str):
    """确保路径存在"""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def _split_conversation_variant(conversation_id: str):
    """
    将 conversation_id 中的 _generated / _corrected / _graded 后缀拆分出来，
    返回 (base_id, variant)
    """
    for suffix in VARIANT_SUFFIXES:
        marker = f"_{suffix}"
        if conversation_id.endswith(marker):
            base = conversation_id[: -len(marker)]
            return base or conversation_id, suffix
    return conversation_id, None


def _get_bank_file_path(conversation_id: str, filename: str = "question_bank.json") -> str:
    """获取题库文件路径（支持多种 variant 和自定义文件名）
    Args:
        conversation_id: 会话ID
        filename: 文件名，默认为 "question_bank.json"
    """
    base_id, variant = _split_conversation_variant(conversation_id)
    if variant:
        folder = os.path.join(BASE_DATA_DIR, base_id, variant)
    else:
        folder = os.path.join(BASE_DATA_DIR, base_id, "quiz")
    _ensure_dir(folder)
    return os.path.join(folder, filename)


def _get_legacy_bank_file_path(conversation_id: str) -> Optional[str]:
    """旧版本路径（conversation_id 直接带后缀）"""
    base_id, variant = _split_conversation_variant(conversation_id)
    if not variant:
        return None
    folder = os.path.join(BASE_DATA_DIR, f"{base_id}_{variant}", "quiz")
    return os.path.join(folder, "question_bank.json")

def _convert_table_html_to_markdown(html_table: str) -> str:
    """将HTML表格转换为Markdown表格
    Args:
        html_table: HTML格式的表格字符串
    Returns:
        Markdown格式的表格字符串
    """
    import re
    
    if not html_table or '<table' not in html_table.lower():
        return html_table
    
    try:
        # 提取表格内容
        table_match = re.search(r'<table[^>]*>(.*?)</table>', html_table, re.DOTALL | re.IGNORECASE)
        if not table_match:
            return html_table
        
        table_content = table_match.group(1)
        
        # 提取所有行
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_content, re.DOTALL | re.IGNORECASE)
        if not rows:
            return html_table
        
        markdown_rows = []
        for i, row in enumerate(rows):
            # 提取单元格（th或td）
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL | re.IGNORECASE)
            if cells:
                # 清理单元格内容
                clean_cells = []
                for cell in cells:
                    # 移除HTML标签，保留文本
                    cell_text = re.sub(r'<[^>]+>', '', cell)
                    # 移除多余空白
                    cell_text = ' '.join(cell_text.split())
                    clean_cells.append(cell_text)
                
                # 构建Markdown行
                markdown_rows.append('| ' + ' | '.join(clean_cells) + ' |')
                
                # 第一行后添加分隔符
                if i == 0:
                    markdown_rows.append('| ' + ' | '.join(['---'] * len(clean_cells)) + ' |')
        
        # 替换原HTML表格
        markdown_table = '\n'.join(markdown_rows)
        result = html_table.replace(table_match.group(0), '\n' + markdown_table + '\n')
        return result
        
    except Exception as e:
        print(f"[⚠️ 表格转换失败] {e}")
        return html_table

def _convert_stem_to_format(stem: str, target_format: str) -> str:
    """转换题干中的表格格式
    Args:
        stem: 题干文本
        target_format: 目标格式 ("html" 或 "markdown")
    Returns:
        转换后的题干
    """
    if not stem:
        return stem
    
    if target_format == "markdown":
        # HTML -> Markdown
        return _convert_table_html_to_markdown(stem)
    else:
        # 暂不支持Markdown -> HTML转换（因为原始就是HTML）
        return stem

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


def save_dual_format_question_bank(conversation_id: str, question_bank: QuestionBank) -> dict:
    """保存双格式题库（HTML + Markdown）
    Args:
        conversation_id: 会话ID
        question_bank: 题库对象（题干为HTML格式）
    Returns:
        包含两个文件路径的字典 {"html": str, "markdown": str}
    """
    # 1. 保存HTML版本（原始格式，用于显示）
    html_path = save_question_bank(conversation_id, question_bank)
    
    # 2. 创建Markdown版本（用于LLM分析）
    markdown_bank = QuestionBank(questions=[])
    for q in question_bank.questions:
        # 转换题干中的表格为Markdown
        markdown_stem = _convert_stem_to_format(q.stem, "markdown")
        
        # 创建新问题对象
        markdown_q = q.model_copy()
        markdown_q.stem = markdown_stem
        markdown_bank.questions.append(markdown_q)
    
    # 3. 保存Markdown版本
    markdown_path = _get_bank_file_path(conversation_id, "question_bank_markdown.json")
    data = {
        "conversation_id": conversation_id,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question_count": len(markdown_bank.questions),
        "question_bank": markdown_bank.model_dump()
    }
    
    with open(markdown_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已保存双格式题库: HTML={html_path}, Markdown={markdown_path}")
    
    return {
        "html": html_path,
        "markdown": markdown_path
    }



def load_question_bank(conversation_id: str) -> Optional[QuestionBank]:
    """
    从磁盘加载题库（HTML格式，用于显示）
    Args:
        conversation_id: 会话ID
    Returns:
        QuestionBank 实例或 None
    """
    return load_question_bank_by_format(conversation_id, "html")


def load_question_bank_by_format(conversation_id: str, format_type: str = "html") -> Optional[QuestionBank]:
    """根据格式加载题库
    Args:
        conversation_id: 对话ID
        format_type: "html" 或 "markdown"
    Returns:
        题库对象，找不到时返回None
    """
    # 确定文件名
    if format_type == "markdown":
        filename = "question_bank_markdown.json"
    else:
        filename = "question_bank.json"
    
    # 构建文件路径
    file_path = _get_bank_file_path(conversation_id, filename)
    
    if not os.path.exists(file_path):
        # 回退到旧路径（仅 HTML）
        if format_type == "html":
            legacy_path = _get_legacy_bank_file_path(conversation_id)
            if legacy_path and os.path.exists(legacy_path):
                file_path = legacy_path
            else:
                return None
        else:
            # 如果请求Markdown但不存在，尝试加载HTML
            print(f"[🔄 Markdown题库不存在，回退到HTML] {conversation_id}")
            return load_question_bank_by_format(conversation_id, "html")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        qb_data = raw.get("question_bank")
        if not qb_data:
            return None

        return QuestionBank(**qb_data)
    except Exception as e:
        print(f"[❌ 加载题库失败] {file_path}: {e}")
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
