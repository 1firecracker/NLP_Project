# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_f_quality_control.py
# 功能：Agent F - 出题质量控制、语言统一、知识点覆盖与重复检测
# ===========================================================

import re
import json
import aiohttp
import asyncio
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import save_question_bank, load_question_bank
from app.agents.models.quiz_models import Question, QuestionBank

API_URL = "https://api.siliconflow.cn/v1"
API_KEY = None
MODEL_NAME = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ===========================================================
# 基础工具函数
# ===========================================================
def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))

def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    cjk_ratio = len(re.findall(r"[\u4e00-\u9fff]", text)) / max(len(text), 1)
    return "Chinese" if cjk_ratio > 0.15 else "English"

# ===========================================================
# LLM 翻译模块
# ===========================================================
async def async_rewrite_to_english(session, q: dict):
    """调用 LLM 将题目翻译成纯英文版本"""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一个严格的语言校对助手，负责将试题翻译成纯英文输出，保持原字段结构。"},
            {"role": "user", "content": f"请将以下JSON题目翻译成英文，不改变字段结构：\n{json.dumps(q, ensure_ascii=False)}"}
        ],
        "max_tokens": 1000,
        "temperature": 0.3
    }
    try:
        async with session.post(f"{API_URL}/chat/completions", headers=HEADERS, json=payload, timeout=120) as resp:
            res = await resp.json()
            content = res["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", content, re.S)
            if match:
                return json.loads(match.group(0))
    except Exception as e:
        print(f"[⚠️ 翻译失败] {e}")
    return q

# ===========================================================
# 知识点覆盖率分析
# ===========================================================
def _norm_kp(kp: str) -> str:
    """简单归一化：去空白、全角转半角、统一小写"""
    if kp is None:
        return ""
    s = str(kp).strip().lower()
    # 可按需扩展：全角转半角、去标点等
    return s

def analyze_knowledge_coverage_binary(qb: QuestionBank):
    """
    二值覆盖率：
    - 从 Agent C 的 distribution_model['knowledge_point_distribution'] 取“期望知识点集合”
    - 从生成题库中汇总所有 knowledge_points，取“实际命中集合”
    - 覆盖率 = 命中集合大小 / 期望集合大小
    - 同时输出每个知识点是否被覆盖（1/0），以及未覆盖清单
    """
    dist_model = getattr(shared_state, "distribution_model", None)
    if not dist_model or "knowledge_point_distribution" not in dist_model:
        print("[⚠️ 无法进行知识点覆盖分析：未找到分布模型或 KP 分布]")
        return {"coverage_rate": 0.0, "covered_map": {}, "missing": []}

    expected_kps_raw = list(dist_model["knowledge_point_distribution"].keys())
    expected_set = {_norm_kp(kp) for kp in expected_kps_raw if kp}

    # 汇总生成题库的 KP
    actual_set = set()
    for q in qb.questions:
        for kp in (q.knowledge_points or []):
            actual_set.add(_norm_kp(kp))

    # 逐点二值命中表
    covered_map = {}
    for kp in expected_kps_raw:
        nk = _norm_kp(kp)
        covered_map[kp] = 1 if nk in actual_set else 0

    hit = sum(covered_map.values())
    total = max(len(expected_set), 1)
    coverage_rate = hit / total

    # 输出报告
    print("\n📊 [F] 知识点二值覆盖率：")
    for kp in expected_kps_raw:
        print(f"  - {kp}: {covered_map[kp]}")

    missing = [kp for kp in expected_kps_raw if covered_map[kp] == 0]
    if missing:
        print(f"  ⚠️ 未覆盖知识点（{len(missing)}）: {missing}")
    else:
        print("  ✅ 期望知识点已全部覆盖。")

    return {"coverage_rate": coverage_rate, "covered_map": covered_map, "missing": missing}

# ===========================================================
# 重复度检测
# ===========================================================
def detect_duplicates(qb: QuestionBank, threshold=0.85):
    stems = [q.stem for q in qb.questions]
    vectorizer = TfidfVectorizer(stop_words="english")
    X = vectorizer.fit_transform(stems)
    sim_matrix = cosine_similarity(X)
    print("\n🔍 [F] 题干重复度检测：")
    duplicates = []
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            if sim_matrix[i, j] > threshold:
                duplicates.append((qb.questions[i].id, qb.questions[j].id, sim_matrix[i, j]))
                print(f"  ⚠️ Q{i+1:03d} 与 Q{j+1:03d} 相似度 {sim_matrix[i,j]:.2f}")
    if not duplicates:
        print("  ✅ 未发现高度相似的题目。")
    return duplicates

# ===========================================================
# 异步主任务
# ===========================================================
async def async_quality_control(qb: QuestionBank, expected_lang="English"):
    async with aiohttp.ClientSession() as session:
        new_questions = []
        for q in qb.questions:
            q_dict = q.__dict__
            lang = detect_language(q.stem)
            if lang != expected_lang:
                print(f"[F] 检测到语言不一致：{q.id} ({lang} → {expected_lang})，开始自动翻译...")
                q_dict = await async_rewrite_to_english(session, q_dict)
            for field in ["stem", "answer", "difficulty", "knowledge_points", "question_type"]:
                if not q_dict.get(field):
                    print(f"[⚠️ 缺失字段] {q.id} → {field}")
            new_questions.append(Question(**q_dict))
        return QuestionBank(questions=new_questions)

# ===========================================================
# 对外主函数
# ===========================================================
def run_agent_f(conversation_id: str, expected_language="English"):
    print("🧩 [Agent F] 开始质量、语言与一致性校对...")
    qb = getattr(shared_state, "generated_exam", None)
    if qb is None:
        print("⚠️ 未找到内存中的题库，尝试从磁盘加载。")
        qb = load_question_bank(f"{conversation_id}_generated")
    if qb is None:
        print("❌ 无可校对题库。")
        return None

    # Step 1: 语言 & 格式统一
    new_qb = asyncio.run(async_quality_control(qb, expected_lang=expected_language))

    # Step 2: 知识点覆盖率分析
    cov = analyze_knowledge_coverage_binary(new_qb)

    # Step 3: 重复度检测
    duplicate_report = detect_duplicates(new_qb, threshold=0.85)

    # Step 4: 保存结果
    save_path = save_question_bank(f"{conversation_id}_corrected", new_qb)
    print(f"\n✅ Agent F 校对完成并保存至: {save_path}")
    print(f"📈 覆盖率(二值): {cov['coverage_rate'] * 100:.2f}%")
    print(f"🔸 未覆盖知识点: {len(cov['missing'])}")
    print(f"🔁 潜在重复题: {len(duplicate_report)} 对\n")
    return new_qb
