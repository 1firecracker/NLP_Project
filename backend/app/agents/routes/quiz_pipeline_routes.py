# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/routes/quiz_pipeline_routes.py
# 功能：FastAPI 路由 — 一键触发出题流水线
# ===========================================================

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form
from typing import List, Optional
import shutil, os

from app.agents.quiz_graph import run_agent_chain, validate_outputs
from app.agents.shared_state import shared_state

router = APIRouter(prefix="/api", tags=["Quiz Pipeline"])

# -----------------------------------------------------------
# 路由1：健康检查
# -----------------------------------------------------------
@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Quiz generation backend running normally.",
        "active_state": list(shared_state.__dict__.keys())
    }

# -----------------------------------------------------------
# 路由2：触发完整出题流水线
# -----------------------------------------------------------
@router.post("/generate_quiz")
async def generate_quiz(
    background_tasks: BackgroundTasks,
    conversation_id: str = Form(...),
    up_to: str = Form("E"),
    expected_language: str = Form("English"),
    files: Optional[List[UploadFile]] = File(None)
):
    """
    一键生成题库。
    - conversation_id: 任务ID
    - up_to: 执行到哪个Agent (A-F)
    - expected_language: Agent F校对目标语言
    - files: 前端上传的PDF/TXT文档（自动保存到 data 临时目录）
    """
    os.makedirs("backend/data/uploads", exist_ok=True)
    file_paths = []

    if files:
        for f in files:
            save_path = os.path.join("backend/data/uploads", f.filename)
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            file_paths.append(save_path)

    # 启动后台任务执行流水线（避免阻塞前端请求）
    background_tasks.add_task(
        run_agent_chain,
        conversation_id,
        file_paths,
        up_to,
        expected_language
    )

    return {
        "status": "started",
        "conversation_id": conversation_id,
        "uploaded_files": file_paths,
        "up_to": up_to
    }

# -----------------------------------------------------------
# 路由3：检查输出文件是否完整
# -----------------------------------------------------------
@router.get("/validate/{conversation_id}")
def validate_pipeline(conversation_id: str):
    """
    检查生成文件的存在性和Agent状态
    """
    checks = validate_outputs(conversation_id)
    return {"conversation_id": conversation_id, "checks": checks}
