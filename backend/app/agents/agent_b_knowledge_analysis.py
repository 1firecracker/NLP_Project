# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/agent_b_knowledge_analysis.py
# 功能：Agent B - 异步知识点覆盖与难度分析
# ===========================================================

import os
import re
import json
import asyncio
import aiohttp
from dotenv import load_dotenv
from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import save_question_bank, load_question_bank
from app.agents.models.quiz_models import QuestionBank

# -----------------------------------------------------------
# 加载 .env 配置
# -----------------------------------------------------------
load_dotenv()
API_URL = os.getenv("LLM_BINDING_HOST", "https://api.siliconflow.cn/v1")
API_KEY = os.getenv("LLM_BINDING_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")

# -----------------------------------------------------------
# 异步 LLM 调用函数
# -----------------------------------------------------------

async def async_analyze_with_llm(session, stem: str, answer: str):
    """
    调用 SiliconFlow 平台的 DeepSeek-R1-Qwen3-8B 模型
    异步分析题目的知识点、难度、题型。
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
你是一名智能教育分析助手。请阅读以下题目和答案，并判断：

1. 主要知识点（列出不超过3个，中文表述）
2. 题型（选择题/简答题/编程题/判断题）
3. 难度等级（easy/medium/hard）

请输出严格的 JSON 格式，不要包含任何解释。

题干：{stem}
答案：{answer}

输出格式：
{{
  "difficulty": "",
  "knowledge_points": [],
  "question_type": ""
}}
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一名严谨的教育分析助手。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 400,
        "temperature": 0.3
    }

    for attempt in range(2):  # ✅ 最多重试两次
        try:
            # 使用 ClientTimeout 设置更长的超时（总共180秒，连接30秒）
            timeout = aiohttp.ClientTimeout(total=500, connect=30, sock_read=150)
            async with session.post(
                f"{API_URL}/chat/completions", 
                headers=headers, 
                json=payload, 
                timeout=timeout
            ) as resp:
                result = await resp.json()
                content = result["choices"][0]["message"]["content"].strip()
                match = re.search(r"\{.*\}", content, re.S)
                if match:
                    content = match.group(0)
                parsed = json.loads(content)
                diff = parsed.get("difficulty", "medium")
                kp = parsed.get("knowledge_points", ["通用知识"])
                qtype = parsed.get("question_type", "short_answer")
                print(f"👉 LLM解析结果: 难度={diff}, 知识点={kp}, 类型={qtype}")
                return diff, kp, qtype
        except asyncio.TimeoutError:
            if attempt == 0:
                print(f"[⚠️ LLM调用超时，重试一次...]")
                await asyncio.sleep(3)
            else:
                print(f"[❌ LLM调用两次均超时，使用默认值]")
                return "medium", ["通用知识"], "short_answer"
        except aiohttp.ClientConnectorError as e:
            # DNS 解析失败或网络连接问题
            if attempt == 0:
                print(f"[⚠️ 网络连接失败，重试一次] {type(e).__name__}")
                await asyncio.sleep(5)  # 网络问题等待更久
            else:
                print(f"[❌ 网络连接两次均失败，使用默认值] {type(e).__name__}")
                return "medium", ["通用知识"], "short_answer"
        except Exception as e:
            if attempt == 0:
                print(f"[⚠️ LLM调用失败，重试一次] {type(e).__name__}: {e}")
                await asyncio.sleep(2)
            else:
                print(f"[❌ LLM调用两次均失败] {type(e).__name__}: {e}")
                return "medium", ["通用知识"], "short_answer"  # ✅ 内部fallback，不再抛出异常


# -----------------------------------------------------------
# 主任务：并发分析整个题库（限制并发数）
# -----------------------------------------------------------

async def async_analyze_question_bank(qb: QuestionBank, max_concurrent: int = 2):
    """
    并发分析所有题目，使用 Semaphore 限制并发数。
    
    Args:
        qb: 题库对象
        max_concurrent: 最大并发数（默认 2，避免 API 限流和网络问题）
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def analyze_with_limit(session, q):
        async with semaphore:
            # 每个请求之间添加小延迟，避免瞬间并发
            await asyncio.sleep(0.5)
            return await async_analyze_with_llm(session, q.stem, q.answer)
    
    async with aiohttp.ClientSession() as session:
        tasks = [analyze_with_limit(session, q) for q in qb.questions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return results


# -----------------------------------------------------------
# Agent B 主函数（外部同步接口）
# -----------------------------------------------------------

def run_agent_b(conversation_id: str):
    """
    Agent B 主函数：
    从 shared_state 或文件加载题库 → 并发调用 LLM → 更新并保存。
    """
    print(f"🧩 [Agent B] 开始知识点与难度分析（异步并发版）...")

    qb: QuestionBank = shared_state.question_bank
    if qb is None or not qb.questions:
        print("⚠️ shared_state.question_bank 为空，尝试从磁盘加载。")
        qb = load_question_bank(conversation_id)

    if qb is None or not qb.questions:
        print("❌ 无可分析题库，Agent B 终止。")
        return None

    print(f"👉 已加载题库，共 {len(qb.questions)} 题。")

    # 运行异步分析（这里本身也要兜底，防止 asyncio.run 直接抛异常）
    try:
        results = asyncio.run(async_analyze_question_bank(qb))
    except Exception as e:
        print(f"[❌ Agent B 异步总调度失败] {type(e).__name__}: {e}")
        # 整体失败：给所有题目填默认值，保证后续 Agent 不至于崩
        for q in qb.questions:
            q.difficulty = getattr(q, "difficulty", "medium")
            q.knowledge_points = getattr(q, "knowledge_points", ["通用知识"])
            q.question_type = getattr(q, "question_type", "short_answer")
        shared_state.question_bank = qb
        save_path = save_question_bank(conversation_id, qb)
        print(f"⚠️ 使用默认难度/知识点/题型保存至: {save_path}")
        return qb

    # 写回结果（逐题兜底处理 Exception）
    for idx, (q, result) in enumerate(zip(qb.questions, results)):
        if isinstance(result, Exception):
            # 这一题的 LLM 调用真的挂了，我们打日志 + 默认值
            print(f"[⚠️ 题目 {q.id} LLM 分析失败，使用默认值] {type(result).__name__}: {result}")
            diff, kp, qtype = "medium", ["通用知识"], "short_answer"
        else:
            diff, kp, qtype = result

        q.difficulty, q.knowledge_points, q.question_type = diff, kp, qtype
        print(f"📘 {q.id}: {q.stem[:25]}... → 难度={diff} | 知识点={kp} | 类型={qtype}")

    # 保存更新结果
    shared_state.question_bank = qb
    save_path = save_question_bank(conversation_id, qb)
    print(f"✅ 异步知识点分析完成并保存至: {save_path}")
    return qb

