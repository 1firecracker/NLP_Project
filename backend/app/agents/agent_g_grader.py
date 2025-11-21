# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_g_grader.py
# 功能：Agent G - 对 Agent E 生成的题目与答案进行批改与评分
# 说明：自动读取 shared_state.generated_exam 或从磁盘加载，使用 LLM 对每题答案
#      给出分数（0-100）、关键性反馈与改进建议，保存带评分的题库与报告。
# ===========================================================

import os
import re
import json
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv

from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import load_question_bank, save_question_bank
from app.agents.models.quiz_models import QuestionBank
from app.agents.database.question_bank_storage import BASE_DATA_DIR


# Load environment
load_dotenv()
API_URL = os.getenv("LLM_BINDING_HOST", "https://api.siliconflow.cn/v1")
API_KEY = os.getenv("LLM_BINDING_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


async def async_grade_with_llm(session, q_idx: int, q_stem: str, q_answer: str, q_explanation: str = None):
    """
    调用 LLM 对单题进行评分与反馈：输出严格 JSON 格式：
    {"score": int(0-100), "feedback": "...", "issues": ["..."], "suggestion": "..."}
    在失败时返回默认中性评估。
    """
    prompt = f"""
你是一个严格的试题批改专家。请根据题干与标准答案/解析对该题的答案质量进行评分与诊断。

要求：
- 给出一个 0-100 的整数分数，100 表示答案完备且解释充分；
- 给出简略反馈（1-2句），标注关键缺陷或亮点；
- 列出 0..n 个具体问题点（issues），例如要点缺失、计算过程错误、格式不规范等；
- 给出一条改进建议（suggestion）。

输入题干：""" + q_stem + """
输入答案：""" + (q_answer or "") + """
解析（若有）：""" + (q_explanation or "") + """

请只输出一个 JSON 对象，且不要包含其他文字。
格式示例：
{"score": 85, "feedback": "回答要点完整，但缺少关键推导步骤。", "issues": ["缺少推导步骤"], "suggestion": "补充第(b)小问中的计算过程并给出中间公式。"}
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一个严谨的试题批改与点评助手。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 600,
        "temperature": 0.0,
    }

    for attempt in range(2):
        try:
            async with session.post(f"{API_URL}/chat/completions", headers=HEADERS, json=payload, timeout=120) as resp:
                res = await resp.json()
                content = res["choices"][0]["message"]["content"].strip()
                # 抽取首个 JSON 对象
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                        # sanitize
                        score = int(parsed.get("score", 50))
                        feedback = parsed.get("feedback", "无反馈")
                        issues = parsed.get("issues", []) or []
                        suggestion = parsed.get("suggestion", "")
                        return {"score": max(0, min(100, score)), "feedback": feedback, "issues": issues, "suggestion": suggestion}
                    except Exception:
                        # parsing error -> fallback try to parse more loosely
                        pass
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(1)
            else:
                # 忽略并走后备
                break

    # Fallback: 根据答案内容判断
    # 如果答案为空或明显不完整，给0分；否则给30分建议人工复核
    answer_text = (q_answer or "").strip()
    if not answer_text or len(answer_text) < 5:
        return {"score": 0, "feedback": "答案为空或过于简短，无法评分。", "issues": ["答案缺失"], "suggestion": "请提供完整答案。"}
    return {"score": 30, "feedback": "模型调用失败，无法准确评分，建议人工复核。", "issues": ["自动评分失败"], "suggestion": "请人工检查关键计算或要点是否齐全。"}


async def async_grade_question_bank(qb: QuestionBank):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, q in enumerate(qb.questions, start=1):
            # try to get explanation field if present
            explanation = getattr(q, "explanation", None)
            tasks.append(asyncio.create_task(async_grade_with_llm(session, idx, q.stem or "", q.answer or "", explanation)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


def run_agent_g(conversation_id: str, expected_language: str = "English"):
    """
    Agent G 主函数：对 Agent E 生成的题库进行逐题批改并生成质量报告。
    - 从 shared_state.generated_exam 或磁盘加载生成题库
    - 并发调用 LLM 获取评分与反馈
    - 将评分写回题库对象（为每题增加 `grade` 和 `grade_feedback` 字段）
    - 保存带评分的题库，并写概要报告到同目录下
    """
    print("🧩 [Agent G] 开始对生成题库进行批改与评分...")

    qb: QuestionBank = getattr(shared_state, "generated_exam", None)
    if qb is None or not getattr(qb, "questions", None):
        print("⚠️ shared_state.generated_exam 为空，尝试从磁盘加载。")
        qb = load_question_bank(f"{conversation_id}_generated")

    if qb is None or not getattr(qb, "questions", None):
        print("❌ 未找到可批改的生成题库，Agent G 终止。")
        return None

    print(f"👉 准备对 {len(qb.questions)} 题进行批改（conversation: {conversation_id}）。")

    # 运行异步批改
    try:
        results = asyncio.run(async_grade_question_bank(qb))
    except Exception as e:
        print(f"[❌ Agent G 调度异常] {type(e).__name__}: {e}")
        return None

    # 写回分数与反馈
    total = 0
    count = 0
    per_question_reports = []
    for q, r in zip(qb.questions, results):
        if isinstance(r, Exception):
            report = {"score": 0, "feedback": "LLM 异常，无法评分，建议人工复核。", "issues": ["评分失败"], "suggestion": "人工复核"}
            print(f"[⚠️ 题目 {q.id} 批改失败，给予0分] {r}")
        else:
            report = r

        # attach to question (best-effort, Question model may accept extra attrs)
        try:
            setattr(q, "grade", report.get("score"))
            setattr(q, "grade_feedback", report.get("feedback"))
            setattr(q, "grade_issues", report.get("issues"))
            setattr(q, "grade_suggestion", report.get("suggestion"))
        except Exception:
            pass

        per_question_reports.append({"id": getattr(q, "id", None), "score": report.get("score"), "feedback": report.get("feedback")})
        total += int(report.get("score", 50) or 0)
        count += 1

    avg_score = (total / max(count, 1)) if count else 0

    # 生成整体质量报告
    quality_report = {
        "conversation_id": conversation_id,
        "graded_at": datetime.now().isoformat(),
        "question_count": count,
        "average_score": avg_score,
        "per_question": per_question_reports,
    }

    # 存入共享状态
    try:
        shared_state.quality_report = quality_report
        shared_state.generated_exam = qb
    except Exception:
        pass

    # 保存带评分的题库（使用已有保存函数）
    try:
        save_path = save_question_bank(f"{conversation_id}_graded", qb)
        # 写入并行的 JSON report 文件旁
        if save_path:
            report_path = os.path.splitext(save_path)[0] + "_grade_report.json"
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(quality_report, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[⚠️ 无法写入报告文件] {e}")

        print(f"✅ 批改完成并保存至: {save_path}")
    except Exception as e:
        print(f"[⚠️ 保存批改结果失败] {e}")

    print(f"📊 平均分: {avg_score:.2f}（共 {count} 题）")
    return quality_report


async def async_grade_student_answer(session, q: dict, student_answer: str):
    """使用 LLM 对单个学生答案进行评分与反馈。返回 {score, feedback, issues}"""
    ref_answer = q.get("answer") or ""
    stem = q.get("stem") or ""

    prompt = f"""
你是严格的阅卷老师。给出题干、参考答案和学生答案，请对学生答案给出：
1) score（0-100 整数），2) 简短评语 feedback, 3) 列表 issues（要点缺失/错误/格式问题等）。

题干：{stem}
参考答案：{ref_answer}
学生答案：{student_answer}

只输出 JSON 对象：{{"score": int, "feedback": str, "issues": [str]}}
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一个严谨的阅卷评分助手。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 400,
        "temperature": 0.0
    }

    for attempt in range(2):
        try:
            async with session.post(f"{API_URL}/chat/completions", headers=HEADERS, json=payload, timeout=120) as resp:
                res = await resp.json()
                content = res["choices"][0]["message"]["content"].strip()
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                        score = int(parsed.get("score", 0))
                        feedback = parsed.get("feedback", "")
                        issues = parsed.get("issues", []) or []
                        return {"score": max(0, min(100, score)), "feedback": feedback, "issues": issues}
                    except Exception:
                        pass
        except Exception:
            if attempt == 0:
                await asyncio.sleep(1)
            else:
                break

    # fallback: simple heuristic
    # exact match for single choice or short answer
    norm_student = (student_answer or "").strip().lower()
    norm_ref = (ref_answer or "").strip().lower()
    if not norm_student:
        return {"score": 0, "feedback": "未作答", "issues": ["空答"]}
    if norm_student == norm_ref:
        return {"score": 100, "feedback": "答案完全匹配参考答案", "issues": []}
    # 检查是否包含参考答案的关键部分（简单的部分匹配）
    if norm_ref in norm_student or norm_student in norm_ref:
        return {"score": 80, "feedback": "答案基本正确", "issues": []}
    # 完全不匹配时给0分
    return {"score": 0, "feedback": "答案与参考答案不符", "issues": ["答案错误"]}


async def async_grade_submission(qb: QuestionBank, answers_map: dict):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for q in qb.questions:
            qdict = q.model_dump() if hasattr(q, 'model_dump') else q.__dict__
            qid = qdict.get('id')
            student_ans = answers_map.get(qid, '')
            tasks.append(asyncio.create_task(async_grade_student_answer(session, qdict, student_ans)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


def run_grade_student_submission(conversation_id: str, student_name: str, answers_map: dict):
    """
    对学生提交（answers_map: {questionId: answer}）进行评分。
    返回 report dict，并保存到 data/<conversation_id>/submissions/*.json
    """
    print(f"🧩 [Agent G] 开始对学生提交进行评分: conversation={conversation_id}, student={student_name}")

    qb = getattr(shared_state, 'generated_exam', None)
    if qb is None or not getattr(qb, 'questions', None):
        qb = load_question_bank(f"{conversation_id}_generated")

    if qb is None or not getattr(qb, 'questions', None):
        raise ValueError('未找到生成题库，无法评分')

    try:
        results = asyncio.run(async_grade_submission(qb, answers_map))
    except Exception as e:
        raise e

    per_q = []
    total = 0
    count = 0
    # knowledge aggregation
    kp_scores = {}
    kp_counts = {}

    for q, r in zip(qb.questions, results):
        qdict = q.model_dump() if hasattr(q, 'model_dump') else q.__dict__
        qid = qdict.get('id')
        student_ans = answers_map.get(qid, '')
        if isinstance(r, Exception):
            rec = {"score": 0, "feedback": '评分异常，需人工复核', "issues": []}
        else:
            rec = r

        per_q.append({
            "id": qid,
            "question_type": qdict.get('question_type'),
            "studentAnswer": student_ans,
            "score": rec.get('score'),
            "feedback": rec.get('feedback'),
            "issues": rec.get('issues', []),
            "knowledge_points": qdict.get('knowledge_points', [])
        })

        total += int(rec.get('score', 0) or 0)
        count += 1

        for kp in qdict.get('knowledge_points', []) or []:
            kp_scores[kp] = kp_scores.get(kp, 0) + rec.get('score', 0)
            kp_counts[kp] = kp_counts.get(kp, 0) + 1

    avg = total / max(count, 1)

    knowledgeAnalysis = {}
    for kp, s in kp_scores.items():
        cnt = kp_counts.get(kp, 1)
        mastery = (s / (cnt * 100)) if cnt else 0
        performance = '优秀' if mastery >= 0.8 else ('良好' if mastery >= 0.6 else '需改进')
        knowledgeAnalysis[kp] = {"masteryLevel": round(mastery, 3), "questionCount": cnt, "performance": performance}

    recommendations = []
    for kp, info in knowledgeAnalysis.items():
        if info['masteryLevel'] < 0.6:
            recommendations.append(f"知识点 {kp} 需加强，建议针对相关题型做专项练习")

    report = {
        "conversation_id": conversation_id,
        "student_name": student_name,
        "graded_at": datetime.now().isoformat(),
        "question_count": count,
        "average_score": avg,
        "per_question": per_q,
        "knowledgeAnalysis": knowledgeAnalysis,
        "recommendations": recommendations
    }

    # save report to disk
    try:
        subs_dir = os.path.join(BASE_DATA_DIR, conversation_id, 'submissions')
        os.makedirs(subs_dir, exist_ok=True)
        fname = f"submission_{student_name or 'anon'}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        fp = os.path.join(subs_dir, fname)
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[⚠️ 保存学生提交报告失败] {e}")

    return report


if __name__ == "__main__":
    # 方便调试
    run_agent_g("test_a_text")
