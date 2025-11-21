# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_h_learning_advisor.py
# 功能：Agent H - 学习诊断与个性化建议生成
# 说明：接收 Agent G 的评分报告，深度分析学生薄弱点，生成针对性学习路径与资源推荐
# ===========================================================

import os
import re
import json
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, List
from collections import defaultdict

from app.agents.database.question_bank_storage import BASE_DATA_DIR

# 加载环境变量
load_dotenv()
API_URL = os.getenv("LLM_BINDING_HOST", "https://api.siliconflow.cn/v1")
API_KEY = os.getenv("LLM_BINDING_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def analyze_weak_points(grading_report: dict) -> dict:
    """
    分析评分报告，识别薄弱知识点与题型。
    返回：
    {
        "weak_knowledge_points": [{"name": "知识点", "mastery": 0.45, "count": 3, "avg_score": 45}],
        "weak_question_types": [{"type": "简答题", "avg_score": 50, "count": 5}],
        "difficult_questions": [{"id": "Q003", "score": 20, "issues": [...]}],
        "overall_weaknesses": ["计算推导不完整", "概念理解模糊"]
    }
    """
    per_q = grading_report.get("per_question", [])
    kp_analysis = grading_report.get("knowledgeAnalysis", {})
    
    # 1️⃣ 薄弱知识点（掌握度 < 0.6）
    weak_kps = []
    for kp, info in kp_analysis.items():
        mastery = info.get("masteryLevel", 0)
        if mastery < 0.6:
            weak_kps.append({
                "name": kp,
                "mastery": round(mastery, 3),
                "count": info.get("questionCount", 0),
                "performance": info.get("performance", "需改进")
            })
    
    # 按掌握度排序（最弱的排前面）
    weak_kps.sort(key=lambda x: x["mastery"])
    
    # 2️⃣ 薄弱题型（平均分 < 60）
    type_scores = defaultdict(list)
    for q in per_q:
        qtype = q.get("question_type", "unknown")
        score = q.get("score", 0)
        type_scores[qtype].append(score)
    
    weak_types = []
    for qtype, scores in type_scores.items():
        avg = sum(scores) / len(scores) if scores else 0
        if avg < 60:
            weak_types.append({
                "type": qtype,
                "avg_score": round(avg, 1),
                "count": len(scores)
            })
    
    weak_types.sort(key=lambda x: x["avg_score"])
    
    # 3️⃣ 得分最低的题目（< 50 分）
    difficult_qs = []
    for q in per_q:
        score = q.get("score", 0)
        if score < 50:
            difficult_qs.append({
                "id": q.get("id"),
                "score": score,
                "feedback": q.get("feedback", ""),
                "issues": q.get("issues", []),
                "knowledge_points": q.get("knowledge_points", [])
            })
    
    difficult_qs.sort(key=lambda x: x["score"])
    
    # 4️⃣ 提取常见问题（从 issues 字段汇总）
    all_issues = []
    for q in per_q:
        all_issues.extend(q.get("issues", []))
    
    # 简单频率统计
    issue_count = defaultdict(int)
    for issue in all_issues:
        issue_count[issue] += 1
    
    # 取前 5 个最常见问题
    overall_weaknesses = sorted(issue_count.items(), key=lambda x: -x[1])[:5]
    overall_weaknesses = [issue for issue, _ in overall_weaknesses]
    
    return {
        "weak_knowledge_points": weak_kps[:5],  # 最多 5 个
        "weak_question_types": weak_types[:3],  # 最多 3 个
        "difficult_questions": difficult_qs[:5],  # 最多 5 题
        "overall_weaknesses": overall_weaknesses
    }


async def async_generate_learning_plan(session, weak_analysis: dict, student_name: str = "该学生"):
    """
    使用 LLM 根据薄弱点分析生成个性化学习计划。
    返回：
    {
        "priority_topics": [{"topic": "知识点A", "reason": "...", "resources": [...]}],
        "study_plan": "分阶段学习建议...",
        "practice_suggestions": ["建议1", "建议2"],
        "estimated_hours": 10
    }
    """
    weak_kps = weak_analysis.get("weak_knowledge_points", [])
    weak_types = weak_analysis.get("weak_question_types", [])
    weaknesses = weak_analysis.get("overall_weaknesses", [])
    
    # 构造 prompt
    prompt = f"""
你是一名经验丰富的教育顾问。请根据以下学生（{student_name}）的考试薄弱点分析，生成个性化学习建议：

【薄弱知识点】
"""
    for kp in weak_kps[:3]:
        prompt += f"- {kp['name']}（掌握度：{kp['mastery']*100:.1f}%，涉及 {kp['count']} 题）\n"
    
    prompt += "\n【薄弱题型】\n"
    for wt in weak_types:
        prompt += f"- {wt['type']}（平均分：{wt['avg_score']}）\n"
    
    prompt += "\n【常见问题】\n"
    for w in weaknesses[:3]:
        prompt += f"- {w}\n"
    
    prompt += """
请生成以下内容（严格 JSON 格式）：
{
  "priority_topics": [
    {"topic": "知识点名称", "reason": "为什么优先学习（1句话）", "resources": ["资源建议1", "资源建议2"]}
  ],
  "study_plan": "分阶段学习计划（3-5 个阶段，每阶段 1-2 句话）",
  "practice_suggestions": ["具体练习建议1", "具体练习建议2", "..."],
  "estimated_hours": 预估需要的学习时长（小时，整数）
}

只输出 JSON，不要其他文字。
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一名专业的教育规划顾问，擅长根据学生表现生成针对性学习方案。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1200,
        "temperature": 0.7
    }

    for attempt in range(2):
        try:
            async with session.post(f"{API_URL}/chat/completions", headers=HEADERS, json=payload, timeout=180) as resp:
                res = await resp.json()
                content = res["choices"][0]["message"]["content"].strip()
                
                # 提取 JSON
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                        return parsed
                    except Exception:
                        pass
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(2)
            else:
                print(f"[⚠️ LLM 生成学习计划失败] {e}")
                break
    
    # Fallback：基于规则生成简单建议
    priority = []
    for kp in weak_kps[:3]:
        priority.append({
            "topic": kp["name"],
            "reason": f"当前掌握度仅 {kp['mastery']*100:.0f}%，需要重点加强",
            "resources": ["复习教材相关章节", "完成课后习题", "观看相关视频教程"]
        })
    
    suggestions = [
        "每天至少复习 1 小时薄弱知识点",
        "完成 10-15 道相关练习题并总结错题",
        "尝试用自己的话解释概念，检验理解深度"
    ]
    
    if weak_types:
        suggestions.append(f"针对 {weak_types[0]['type']} 进行专项训练")
    
    return {
        "priority_topics": priority,
        "study_plan": "第一阶段：巩固薄弱知识点基础概念（2-3 天）；第二阶段：针对性练习与错题分析（3-4 天）；第三阶段：综合应用与模拟测试（2 天）。",
        "practice_suggestions": suggestions,
        "estimated_hours": len(weak_kps) * 3 + 5  # 粗略估计
    }


def run_agent_h(grading_report: dict, conversation_id: str, student_name: str = "学生") -> dict:
    """
    Agent H 主函数：接收评分报告，生成学习诊断与建议。
    
    Args:
        grading_report: Agent G 返回的评分报告
        conversation_id: 会话 ID
        student_name: 学生姓名
    
    Returns:
        dict: 包含薄弱点分析 + 学习计划的完整报告
    """
    print(f"🧩 [Agent H] 开始生成学习诊断与建议（学生：{student_name}）...")
    
    # 1️⃣ 分析薄弱点
    weak_analysis = analyze_weak_points(grading_report)
    
    # 2️⃣ 调用 LLM 生成学习计划
    try:
        async def main():
            async with aiohttp.ClientSession() as session:
                return await async_generate_learning_plan(session, weak_analysis, student_name)
        
        learning_plan = asyncio.run(main())
    except Exception as e:
        print(f"[❌ Agent H LLM 调用失败] {e}")
        # 使用降级方案
        learning_plan = {
            "priority_topics": [],
            "study_plan": "请根据薄弱知识点，系统复习相关章节并完成配套练习。",
            "practice_suggestions": ["复习错题", "完成课后习题"],
            "estimated_hours": 8
        }
    
    # 3️⃣ 组合完整报告
    h_report = {
        "conversation_id": conversation_id,
        "student_name": student_name,
        "generated_at": datetime.now().isoformat(),
        "weak_analysis": weak_analysis,
        "learning_plan": learning_plan,
        "summary": {
            "weak_kp_count": len(weak_analysis["weak_knowledge_points"]),
            "difficult_q_count": len(weak_analysis["difficult_questions"]),
            "priority_count": len(learning_plan.get("priority_topics", [])),
            "estimated_hours": learning_plan.get("estimated_hours", 0)
        }
    }
    
    # 4️⃣ 保存到磁盘
    try:
        advisor_dir = os.path.join(BASE_DATA_DIR, conversation_id, "learning_advice")
        os.makedirs(advisor_dir, exist_ok=True)
        fname = f"advice_{student_name or 'anon'}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        fp = os.path.join(advisor_dir, fname)
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(h_report, f, ensure_ascii=False, indent=2)
        print(f"✅ 学习建议已保存至: {fp}")
    except Exception as e:
        print(f"[⚠️ 保存学习建议失败] {e}")
    
    print(f"📚 [Agent H] 完成学习诊断：识别 {h_report['summary']['weak_kp_count']} 个薄弱知识点，"
          f"生成 {h_report['summary']['priority_count']} 个优先学习主题。")
    
    return h_report


if __name__ == "__main__":
    # 测试用例
    mock_report = {
        "per_question": [
            {"id": "Q001", "score": 80, "question_type": "选择题", "issues": [], "knowledge_points": ["Python基础"]},
            {"id": "Q002", "score": 40, "question_type": "简答题", "issues": ["缺少推导步骤"], "knowledge_points": ["数据结构"]},
            {"id": "Q003", "score": 30, "question_type": "编程题", "issues": ["逻辑错误", "语法错误"], "knowledge_points": ["算法", "循环"]},
        ],
        "knowledgeAnalysis": {
            "Python基础": {"masteryLevel": 0.8, "questionCount": 1, "performance": "良好"},
            "数据结构": {"masteryLevel": 0.4, "questionCount": 1, "performance": "需改进"},
            "算法": {"masteryLevel": 0.3, "questionCount": 1, "performance": "需改进"},
        }
    }
    
    result = run_agent_h(mock_report, "test_conv", "测试学生")
    print(json.dumps(result, ensure_ascii=False, indent=2))
