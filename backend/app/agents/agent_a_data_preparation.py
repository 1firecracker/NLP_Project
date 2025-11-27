# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_a_data_preparation.py
# 功能：Agent A - 扫描 Markdown 样卷 → 调用 LLM 生成含题型/难度/知识点的多层题库 → QuestionBank
# ===========================================================

import json
import os
import re
import time
from collections import Counter
from typing import List, Tuple, Dict

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

PROMPT_TEMPLATE = """你是一名“试题抽取与结构化助手”。输入是一份 Markdown 试卷，题目编号、分值和子问标记形式可能不统一。请严格输出 JSON 数组，每道题及其子题都要包含题型、难度（easy/medium/hard）和知识点：
[
  {{
    "id": "题目编号（如 1、2、3、1(a)）",
    "stem": "题干全文（去掉题号、分值提示）",
    "score": 题目总分（数字，缺失填 0）,
    "question_type": "short_answer | calculation | multiple_choice | single_choice | essay | programming | other",
    "difficulty": "easy | medium | hard",
    "knowledge_points": ["知识点1", "知识点2"],
    "sub_questions": [
        {{
            "label": "子问标记（a/i 等）",
            "stem": "子问题内容",
            "score": 子问分值（数字，缺失填 0）,
            "question_type": "子题题型，同上取值范围",
            "difficulty": "easy | medium | hard",
            "knowledge_points": ["知识点A", "知识点B"],
            "sub_questions": [
                {{
                    "label": "更细一级子问标记（如 a-1/i/1 等）",
                    "stem": "更细一级子问内容",
                    "score": 子问分值（数字，缺失填 0）,
                    "question_type": "子题题型，同上取值范围",
                    "difficulty": "easy | medium | hard",
                    "knowledge_points": ["知识点X"]
                }}
            ]
        }}
    ]
  }}
]
- 如果题目没有子问，sub_questions 设为空数组；若子问下还有子问，继续递归使用上述字段。
- 分值缺失填 0；题型无法判断填 other；知识点至少给出一项（确实无法识别可使用 ["通用知识"]）。
- 保留 Markdown/LaTeX 公式内容，只输出合法 JSON，不要添加额外解释或代码块标记。

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
    
    def _safe_load(candidate: str):
        """处理 LaTeX 转义字符"""
        fixed = candidate
        # 修复 LaTeX 中常见的非法 JSON 转义
        latex_escapes = [
            (r'\{', r'\\{'),
            (r'\}', r'\\}'),
            (r'\(', r'\\('),
            (r'\)', r'\\)'),
            (r'\[', r'\\['),
            (r'\]', r'\\]'),
            (r'\_', r'\\_'),
            (r'\^', r'\\^'),
            (r'\&', r'\\&'),
            (r'\%', r'\\%'),
            (r'\$', r'\\$'),
            (r'\#', r'\\#'),
        ]
        for old, new in latex_escapes:
            fixed = re.sub(r'(?<!\\)' + re.escape(old), new, fixed)
        return json.loads(fixed)

    def _find_balanced_json_array(s: str, start_pos: int = 0) -> str:
        """使用括号匹配找到完整的 JSON 数组"""
        arr_start = s.find('[', start_pos)
        if arr_start == -1:
            return None
        
        bracket_count = 0
        in_string = False
        escape_next = False
        
        for i in range(arr_start, len(s)):
            char = s[i]
            
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
                        return s[arr_start:i+1]
        
        return None

    # 1. 先去除 ```json ... ``` 代码块标记
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if code_block_match:
        text = code_block_match.group(1).strip()
        print(f"[📝 检测到代码块，已提取内容]")

    # 2. 尝试直接解析整个文本
    if text.startswith('['):
        try:
            return _safe_load(text)
        except json.JSONDecodeError as e:
            print(f"[⚠️ 直接解析失败] {e}")
    
    # 3. 使用括号匹配找到完整的 JSON 数组
    json_str = _find_balanced_json_array(text)
    if json_str:
        try:
            return _safe_load(json_str)
        except json.JSONDecodeError as e:
            print(f"[⚠️ JSON 解析失败] {e}")
            # 尝试修复尾部逗号
            try:
                fixed = re.sub(r',\s*}', '}', json_str)
                fixed = re.sub(r',\s*]', ']', fixed)
                return _safe_load(fixed)
            except:
                pass
    
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
        "max_tokens": 4000,
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
                        "thinking_budget": 256
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
        difficulty_raw = entry.get("difficulty", "medium")
        difficulty = str(difficulty_raw).strip() if difficulty_raw is not None else "medium"
        kp_raw = entry.get("knowledge_points", [])
        kp_list = []
        if isinstance(kp_raw, list):
            kp_list = [str(k).strip() for k in kp_raw if str(k).strip()]
        if not kp_list:
            kp_list = ["通用知识"]
        child_entries = entry.get("sub_questions", [])
        children = _parse_sub_questions(child_entries) if isinstance(child_entries, list) else []
        label_final = label if label else f"sub_{index}"
        parsed.append(
            SubQuestion(
                label=label_final,
                stem=stem,
                score=score,
                question_type=qtype or "short_answer",
                difficulty=difficulty or "medium",
                knowledge_points=kp_list,
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
        difficulty_raw = item.get("difficulty", "medium")
        difficulty = str(difficulty_raw).strip() if difficulty_raw is not None else "medium"
        kp_raw = item.get("knowledge_points", [])
        kp_list = []
        if isinstance(kp_raw, list):
            kp_list = [str(k).strip() for k in kp_raw if str(k).strip()]
        if not kp_list:
            kp_list = ["通用知识"]
        sub_questions = _parse_sub_questions(item.get("sub_questions", []))

        tags = [f"source:{source_label}", f"score:{score}"]

        question = Question(
            id=qid if qid else f"Q{idx:03d}",
            stem=stem,
            answer="（待补充）",
            difficulty=difficulty or "medium",
            knowledge_points=kp_list,
            question_type=qtype or "short_answer",
            tags=tags,
            sub_questions=sub_questions,
        )
        questions.append(question)
    return questions


def _compute_distribution(questions: List[Question]) -> Dict[str, Dict[str, float]]:
    """
    统计题型/难度/知识点分布，输出与原 Agent C 相同结构：
    {
        "conversation_id": ...,
        "total_questions": ...,
        "type_distribution": {...},
        "difficulty_distribution": {...},
        "knowledge_point_distribution": {...}
    }
    """
    type_counter = Counter()
    difficulty_counter = Counter()
    knowledge_counter = Counter()

    def traverse_question(q: Question):
        type_counter[q.question_type or "未知类型"] += 1
        difficulty_counter[q.difficulty or "medium"] += 1
        if q.knowledge_points:
            for kp in q.knowledge_points:
                if kp:
                    knowledge_counter[kp] += 1
        else:
            knowledge_counter["通用知识"] += 1
        if q.sub_questions:
            for sub in q.sub_questions:
                # 将 SubQuestion 转为 Question 视角统计
                sub_q = Question(
                    id=f"{q.id}-{sub.label}",
                    stem=sub.stem,
                    answer="（子问）",
                    difficulty=sub.difficulty or "medium",
                    knowledge_points=sub.knowledge_points or ["通用知识"],
                    question_type=sub.question_type or "short_answer",
                    tags=[],
                    sub_questions=sub.sub_questions,
                )
                traverse_question(sub_q)

    for q in questions:
        traverse_question(q)

    def _calc(counter: Counter):
        total = sum(counter.values())
        if total == 0:
            return {}
        return {k: round(v / total, 4) for k, v in counter.items()}

    return {
        "total_questions": len(questions),
        "type_distribution": _calc(type_counter),
        "difficulty_distribution": _calc(difficulty_counter),
        "knowledge_point_distribution": _calc(knowledge_counter),
    }


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
    max_retries = 2  # 解析失败时最多重试次数
    
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

        # 带重试的解析逻辑
        llm_items = None
        for retry in range(max_retries + 1):
            attempt_name = f"{source_name}_retry{retry}" if retry > 0 else source_name
            llm_items = extract_questions_via_llm(content, conversation_id, attempt_name)
            if llm_items:
                break
            if retry < max_retries:
                print(f"[🔄 解析结果为空，正在重试 {retry + 1}/{max_retries}] {md_path}")
                time.sleep(1)  # 重试前等待 1 秒
        
        if not llm_items:
            print(f"[❌ 重试 {max_retries} 次后仍未解析到题目] {md_path}")
            continue
            
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

    # 统计分布并写入 shared_state
    distribution = _compute_distribution(all_questions)
    distribution_model = {
        "conversation_id": conversation_id,
        "total_questions": distribution.get("total_questions", len(all_questions)),
        "type_distribution": distribution.get("type_distribution", {}),
        "difficulty_distribution": distribution.get("difficulty_distribution", {}),
        "knowledge_point_distribution": distribution.get("knowledge_point_distribution", {}),
    }
    shared_state.distribution_model = distribution_model

    # 保存分布文件，便于替代 Agent C
    dist_dir = os.path.join(BASE_DIR, "data", conversation_id)
    os.makedirs(dist_dir, exist_ok=True)
    dist_path = os.path.join(dist_dir, "distribution.json")
    with open(dist_path, "w", encoding="utf-8") as f:
        json.dump(distribution_model, f, ensure_ascii=False, indent=2)
    print(f"📊 题型/难度/知识点分布已生成：{dist_path}")

    save_path = save_question_bank(conversation_id, qb)
    print(f"✅ Agent A 完成，共抽取 {len(all_questions)} 题。题库已保存：{save_path}")
    return qb
