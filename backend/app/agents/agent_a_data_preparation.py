# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_a_data_preparation.py
# 功能：Agent A - Markdown 样卷抽题 → QuestionBank
# ===========================================================

import json
import os
import re
import time
from typing import List, Tuple

import requests
from openai import OpenAI  # type: ignore
from dotenv import load_dotenv  # type: ignore

from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import save_question_bank
from app.agents.models.quiz_models import Question, QuestionBank, SubQuestion

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
OPENAI_CLIENT = OpenAI(api_key=API_KEY, base_url=API_URL) if OpenAI else None
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

PROMPT_TEMPLATE = """你是一名“试题抽取与结构化助手”。输入是一份 Markdown 格式的试卷内容，题目编号、
分值和子问标记形式可能不完全统一。请严格按照以下 JSON 模板输出题目数组，并支持子问题递归嵌套：
[
  {{
    "id": "题目编号（如 1, 2, 3 或 1(a)）",
    "stem": "题干全文（去掉题号、分值提示）",
    "score": 题目总分（数字，缺失填 0）,
    "question_type": "short_answer | calculation | multiple_choice | single_choice  | essay ",
    "sub_questions": [
        {{
            "label": "子问标记（a/i 等）",
            "stem": "子问题内容",
            "score": 子问分值（数字，缺失填 0）,
            "question_type": "子题题型，同上取值范围",
            "sub_questions": [
                {{
                    "label": "子问内的子问标记（如 a-1/i - 1/1/2 等）",
                    "stem": "更细一级的子问内容",
                    "score": 子问分值（数字，缺失填 0）,
                    "question_type": "子题题型，同上取值范围"
                }}
            ]
        }}
    ]
  }}
]
- 如果题目没有子问，sub_questions 设为空数组；如果子问下还有子问，继续使用同样结构递归嵌套。
- 若整题或子问缺少分值，填 0；题型无法判断则填 other。
- 保留 Markdown/LaTeX 公式内容。
- 仅输出合法 JSON，不要添加额外解释或代码块标记。

请处理以下 Markdown：
<<<BEGIN_MARKDOWN
{markdown}
<<<END_MARKDOWN
"""

# -----------------------------------------------------------
# Markdown 文件扫描
# -----------------------------------------------------------

def _scan_markdown_files(conversation_id: str, provided_paths: List[str] = None) -> List[str]:
    """
    收集会话下所有 .md 文件。
    """
    if provided_paths:
        sanitized = [
            p for p in provided_paths
            if p and p.strip().upper() != "__AUTO__"
        ]
        if sanitized:
            return [p for p in sanitized if p.lower().endswith(".md") and os.path.exists(p)]

    base_dir = os.path.join(BASE_DIR, "uploads", "exercises", conversation_id, "samples")
    detected = []
    if not os.path.exists(base_dir):
        return detected

    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".md"):
                detected.append(os.path.join(root, f))
    return detected


# -----------------------------------------------------------
# LLM 调用
# -----------------------------------------------------------

def _extract_json_array(text: str):
    """
    从 LLM 输出中提取 JSON 数组，支持嵌套结构。
    优先尝试直接解析整个文本，失败则尝试提取代码块或数组片段。
    """
    if not text:
        return []
    
    text = text.strip()
    
    # 1. 尝试直接解析整个文本
    if text.startswith('['):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    
    # 2. 尝试提取 ```json ... ``` 或 ``` ... ``` 代码块
    code_block_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 3. 尝试提取第一个完整的 JSON 数组（支持嵌套）
    # 使用栈匹配括号，找到完整的 [ ... ] 结构
    start_idx = text.find('[')
    if start_idx == -1:
        return []
    
    bracket_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    # 找到完整数组
                    json_str = text[start_idx:i+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
                    break
    
    return []


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文按字符，英文按空格分词，约 1.3 倍"""
    if not text:
        return 0
    # 简单启发式：中文字符数 + 英文单词数
    import re
    cjk_count = len(re.findall(r'[\u4e00-\u9fff]', text))
    eng_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
    return int((cjk_count + eng_words) * 1.3)



def extract_questions_via_llm(markdown_text: str, conversation_id: str, source_name: str) -> List[dict]:
    """
    调用 LLM 将 Markdown 转为结构化题目列表。
    """
    if not markdown_text.strip():
        return []

    prompt = PROMPT_TEMPLATE.format(markdown=markdown_text)
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一个严谨的试题抽取专家，专门从 Markdown 试卷中定位题目。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
    }
    # payload["response_format"] = {"type": "json_object"}

    # 估算输入 token 数
    total_text = payload["messages"][0]["content"] + payload["messages"][1]["content"]
    est_tokens = _estimate_tokens(total_text)
    print(f"🧾 LLM 预计 tokens: {est_tokens}")

    for attempt in range(2):
        try:
            start_ts = time.time()
            if OPENAI_CLIENT is not None:
                print("open ai client sending successfully")
                response = OPENAI_CLIENT.chat.completions.create(
                    model=MODEL_NAME,
                    messages=payload["messages"],
                    temperature=payload["temperature"],
                    max_tokens=payload["max_tokens"],
                    # response_format=payload["response_format"],
                    extra_body={
                        "thinking_budget": 1
                    }
                )
                cost = time.time() - start_ts
                print(f"⏱️ LLM 请求耗时: {cost:.2f}s")
                content = response.choices[0].message.content or ""
            else:
                resp = requests.post(
                    f"{API_URL}/chat/completions",
                    headers=HEADERS,
                    json=payload,
                    timeout=500,
                )
                cost = time.time() - start_ts
                print(f"⏱️ LLM 请求耗时: {cost:.2f}s")
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

            # 保存原始输出
            debug_dir = os.path.join(BASE_DIR, "data", conversation_id, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, f"agent_a_{source_name}_attempt{attempt+1}.txt")
            with open(debug_file, "w", encoding="utf-8") as dbg:
                dbg.write(content)
            print(f"📝 LLM 原始输出已保存：{debug_file}")

            parsed = _extract_json_array(content)
            if parsed:
                return parsed
            print(f"[⚠️ LLM 返回无法解析 JSON，尝试重试] attempt={attempt+1}")
        except requests.RequestException as e:
            cost = time.time() - start_ts if 'start_ts' in locals() else 0.0
            print(f"⏱️ LLM 请求耗时: {cost:.2f}s")
            print(f"[⚠️ LLM 请求失败 attempt={attempt+1}] {e}")
    return []


# -----------------------------------------------------------
# Question 对象构建
# -----------------------------------------------------------

def _parse_sub_questions(entries: List[dict]) -> List[SubQuestion]:
    """递归解析子问题列表"""
    parsed: List[SubQuestion] = []
    if not isinstance(entries, list):
        return parsed

    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            continue
        label_raw = entry.get("label", "")
        label = str(label_raw).strip() if label_raw is not None else ""
        stem_raw = entry.get("stem", "")
        stem = str(stem_raw).strip() if stem_raw is not None else ""
        if not stem:
            continue
        score_value = entry.get("score", 0)
        if isinstance(score_value, (int, float)):
            score = int(score_value)
        else:
            score = 0
        qtype_raw = entry.get("question_type", "short_answer")
        qtype = str(qtype_raw).strip() if qtype_raw is not None else "short_answer"
        child_entries = entry.get("sub_questions", [])
        children = _parse_sub_questions(child_entries) if isinstance(child_entries, list) else []
        label_final = label if label else f"sub_{index}"
        parsed.append(
            SubQuestion(
                label=label_final,
                stem=stem,
                score=score,
                question_type=qtype or "short_answer",
                sub_questions=children,
            )
        )
    return parsed


def _convert_items_to_questions(items: List[dict], source_label: str) -> List[Question]:
    """
    将 LLM 返回的题目列表转换为 Question 对象，保留嵌套的 sub_questions 结构。
    """
    questions: List[Question] = []
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        stem_raw = item.get("stem", "")
        stem = str(stem_raw).strip() if stem_raw is not None else ""
        if not stem:
            continue
        qid_raw = item.get("id", f"Q{idx:03d}")
        qid = str(qid_raw).strip() if qid_raw is not None else f"Q{idx:03d}"
        qtype_raw = item.get("question_type", "short_answer")
        qtype = str(qtype_raw).strip() if qtype_raw is not None else "short_answer"
        score_value = item.get("score", 0)
        if isinstance(score_value, (int, float)):
            score = int(score_value)
        else:
            score = 0
        sub_questions = _parse_sub_questions(item.get("sub_questions", []))

        tags = [f"source:{source_label}", f"score:{score}"]

        question = Question(
            id=qid if qid else f"Q{idx:03d}",
            stem=stem,
            answer="（待补充）",
            difficulty="medium",
            knowledge_points=[],
            question_type=qtype or "short_answer",
            tags=tags,
            sub_questions=sub_questions,
        )
        questions.append(question)
    return questions


# -----------------------------------------------------------
# 主执行函数
# -----------------------------------------------------------

def run_agent_a(conversation_id: str, file_paths: List[str] = None) -> QuestionBank:
    print(f"🧩 [Agent A] Markdown 抽题开始，会话ID: {conversation_id}")

    md_files = _scan_markdown_files(conversation_id, file_paths)
    if not md_files:
        print(f"⚠️ 会话 {conversation_id} 未找到任何 .md 样卷，返回空题库交由 Agent E 处理。")
        qb = QuestionBank(questions=[], source_docs=[])
        shared_state.question_bank = qb
        shared_state.source_text = ""
        return qb

    print(f"👉 已发现 {len(md_files)} 个 Markdown 样卷：")
    for f in md_files:
        print(f"   - {f}")

    aggregated_texts = []
    all_questions: List[Question] = []
    for md_path in md_files:
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"[⚠️ 无法读取文件] {md_path}: {e}")
            continue

        aggregated_texts.append(f"\n\n# Source: {md_path}\n{content}")
        source_name = os.path.splitext(os.path.basename(md_path))[0]
        relative_name = os.path.relpath(md_path, os.path.join(BASE_DIR, "uploads"))

        llm_items = extract_questions_via_llm(content, conversation_id, source_name)
        if not llm_items:
            print(f"[⚠️ LLM 未从 {md_path} 中解析到题目]")
            continue
        relative_name = os.path.relpath(md_path, os.path.join(BASE_DIR, "uploads"))
        questions = _convert_items_to_questions(llm_items, relative_name)
        all_questions.extend(questions)
        print(f"✅ {md_path} 解析得到 {len(questions)} 道题")

    if not all_questions:
        print("⚠️ 所有 Markdown 样卷均未成功抽取题目，返回空题库交由 Agent E 处理。")
        qb = QuestionBank(questions=[], source_docs=md_files)
        shared_state.question_bank = qb
        shared_state.source_text = "\n".join(aggregated_texts)
        return qb

    qb = QuestionBank(questions=all_questions, source_docs=md_files)
    shared_state.question_bank = qb
    shared_state.source_text = "\n".join(aggregated_texts)

    save_path = save_question_bank(conversation_id, qb)
    print(f"✅ Agent A 完成，共抽取 {len(all_questions)} 题。题库已保存：{save_path}")
    return qb
