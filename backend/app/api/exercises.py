"""样本试题管理API路由"""
from fastapi import APIRouter, File, UploadFile, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, Response
from typing import List
from pydantic import BaseModel
from pathlib import Path
import os
import json

from app.services.exercise_service import ExerciseService
from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import load_question_bank
from app.agents.models.quiz_models import Question
from fastapi.concurrency import run_in_threadpool
from fastapi import Form, File as FFile, UploadFile as FUploadFile
import json
import re

router = APIRouter()


# 响应模型
class SampleUploadResponse(BaseModel):
    """样本试题上传响应"""
    conversation_id: str
    uploaded_samples: List[dict]
    total_samples: int


class SampleListResponse(BaseModel):
    """样本试题列表响应"""
    samples: List[dict]
    total: int

class GenerateQuizResponse(BaseModel):
    """一键生成试题的响应"""
    conversation_id: str
    generated_conversation_id: str
    question_count: int
    pipeline_status: dict
    quality_report: dict | None = None

class GeneratedQuestion(BaseModel):
    """前端用来展示的题目结构（从 QuestionBank 映射而来）"""
    id: str
    stem: str
    options: list[str] | None = None
    answer: str | None = None
    explanation: str | None = None
    difficulty: str | None = None
    knowledge_points: list[str] | None = None
    question_type: str | None = None


class GeneratedQuestionListResponse(BaseModel):
    """生成题目列表响应"""
    conversation_id: str
    question_count: int
    questions: list[GeneratedQuestion]

@router.post(
    "/api/conversations/{conversation_id}/exercises/samples/upload",
    response_model=SampleUploadResponse,
    status_code=status.HTTP_201_CREATED
)
async def upload_samples(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """上传样本试题
    
    支持上传多个文件（PDF/DOCX/TXT格式）
    文件上传后立即返回，解析在后台异步进行
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要上传一个文件"
        )
    
    service = ExerciseService()
    
    try:
        result = await service.upload_samples(conversation_id, files)
        
        # 添加后台任务：异步解析每个文件
        for sample_info in result["uploaded_samples"]:
            sample_id = sample_info["sample_id"]
            sample_dir = service._get_sample_dir(conversation_id, sample_id)
            # 从元数据中获取文件路径，或查找原始文件
            metadata_file = service._get_metadata_file(conversation_id, sample_id)
            original_file_path = None
            
            if metadata_file.exists():
                import json
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    rel_path = metadata.get("original_file_path")
                    if rel_path:
                        original_file_path = sample_dir / rel_path
            
            # 如果元数据中没有路径，查找文件
            if not original_file_path or not original_file_path.exists():
                for f in sample_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in ['.pdf', '.docx', '.txt']:
                        original_file_path = f
                        break
            
            if original_file_path and original_file_path.exists():
                background_tasks.add_task(
                    service._parse_sample_async,
                    conversation_id,
                    sample_id,
                    original_file_path
                )
        
        return SampleUploadResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传样本试题失败: {str(e)}"
        )


@router.get(
    "/api/conversations/{conversation_id}/exercises/samples",
    response_model=SampleListResponse
)
async def list_samples(conversation_id: str):
    """获取样本试题列表"""
    service = ExerciseService()
    
    try:
        samples = service.list_samples(conversation_id)
        return SampleListResponse(
            samples=samples,
            total=len(samples)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取样本试题列表失败: {str(e)}"
        )


@router.get(
    "/api/conversations/{conversation_id}/exercises/samples/{sample_id}"
)
async def get_sample(conversation_id: str, sample_id: str):
    """获取样本试题详情"""
    service = ExerciseService()
    sample = service.get_sample(conversation_id, sample_id)
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"样本试题 {sample_id} 不存在"
        )
    
    return JSONResponse(content=sample)


@router.get(
    "/api/conversations/{conversation_id}/exercises/samples/{sample_id}/status"
)
async def get_sample_status(conversation_id: str, sample_id: str):
    """获取样本试题解析状态"""
    service = ExerciseService()
    sample = service.get_sample(conversation_id, sample_id)
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"样本试题 {sample_id} 不存在"
        )
    
    return {
        "sample_id": sample_id,
        "conversation_id": conversation_id,
        "status": sample.get("status", "unknown"),
        "parse_start_time": sample.get("parse_start_time"),
        "parse_end_time": sample.get("parse_end_time"),
        "error": sample.get("error"),
        "text_length": sample.get("text_length", 0),
        "image_count": sample.get("image_count", 0)
    }


@router.delete(
    "/api/conversations/{conversation_id}/exercises/samples/{sample_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_sample(conversation_id: str, sample_id: str):
    """删除样本试题"""
    service = ExerciseService()
    
    try:
        success = service.delete_sample(conversation_id, sample_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"样本试题 {sample_id} 不存在"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除样本试题失败: {str(e)}"
        )


@router.get(
    "/api/conversations/{conversation_id}/exercises/samples/{sample_id}/text"
)
async def get_sample_text(conversation_id: str, sample_id: str):
    """获取样本试题文本内容"""
    service = ExerciseService()
    
    try:
        text = service.get_sample_text(conversation_id, sample_id)
        if text is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"样本试题 {sample_id} 不存在"
            )
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取样本试题文本失败: {str(e)}"
        )


@router.get(
    "/api/conversations/{conversation_id}/exercises/samples/{sample_id}/images/{image_name}"
)
async def get_sample_image(
    conversation_id: str,
    sample_id: str,
    image_name: str
):
    """获取样本试题图片"""
    from pathlib import Path
    import app.config as config
    
    # 构建图片路径
    exercises_dir = Path(config.settings.exercises_dir)
    image_path = exercises_dir / conversation_id / "samples" / sample_id / "images" / image_name
    
    if not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"图片 {image_name} 不存在"
        )
    
    return FileResponse(
        path=str(image_path),
        media_type=f"image/{Path(image_name).suffix.lstrip('.')}"
    )


@router.get(
    "/api/conversations/{conversation_id}/exercises/samples/{sample_id}/file"
)
async def get_sample_file(
    conversation_id: str,
    sample_id: str
):
    """获取样本试题原始文件"""
    from pathlib import Path
    import app.config as config
    
    service = ExerciseService()
    sample = service.get_sample(conversation_id, sample_id)
    
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"样本试题 {sample_id} 不存在"
        )
    
    # 获取原始文件路径
    sample_dir = service._get_sample_dir(conversation_id, sample_id)
    original_filename = sample.get("original_filename", sample.get("filename", ""))
    file_path = sample_dir / original_filename if original_filename else None
    
    # 如果原始文件不存在，尝试在样本目录中查找
    if not file_path or not file_path.exists():
        for f in sample_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ['.pdf', '.docx', '.txt']:
                file_path = f
                break
    
    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="原始文件不存在"
        )
    
    # 根据文件类型设置 media_type
    file_ext = file_path.suffix.lower()
    media_type_map = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.doc': 'application/msword',
        '.txt': 'text/plain'
    }
    media_type = media_type_map.get(file_ext, 'application/octet-stream')
    
    # 读取文件内容
    with open(file_path, 'rb') as f:
        file_content = f.read()
    
    # 设置响应头，强制内联显示（不下载）
    headers = {
        'Content-Disposition': f'inline; filename="{original_filename}"'
    }
    
    return Response(
        content=file_content,
        media_type=media_type,
        headers=headers
    )

@router.post(
    "/api/conversations/{conversation_id}/exercises/generate",
    response_model=GenerateQuizResponse
)
async def generate_exercises(conversation_id: str):
    """
    基于当前会话上传的样本试卷，启动出题 Agent 链（A~F），
    并返回生成结果概要（题目数量 / 管道状态 / 质量报告等）。
    """
    service = ExerciseService()
    try:
        # 调用我们刚刚在 ExerciseService 里加的逻辑
        result = await run_in_threadpool(service.generate_questions, conversation_id)
        return GenerateQuizResponse(**result)
    except ValueError as e:
        # 比如没有样本、样本还在解析中等
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成题目失败: {e}"
        )

from app.agents.database.question_bank_storage import load_question_bank
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from app.services.exercise_service import ExerciseService

@router.get(
    "/api/conversations/{conversation_id}/exercises/generated_questions"
)
async def get_generated_questions(conversation_id: str):
    """
    获取当前会话最新一次生成的试题列表
    """
    # 1️⃣ 先尝试从内存中的 shared_state 读取（刚刚跑完流水线时会有）
    qb = getattr(shared_state, "generated_exam", None)
    if qb is None or not getattr(qb, "questions", None):
        # 2️⃣ 如果内存里没有，再从磁盘加载  {conversation_id}_generated  这份题库
        qb = load_question_bank(f"{conversation_id}_generated")

    if qb is None or not getattr(qb, "questions", None):
        # 说明当前会话还没生成过题，返回 404，让前端显示“暂无试题”
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前会话尚未生成试题"
        )

    # 兼容 Question 既可能是 Pydantic，也可能是普通 dataclass 的情况
    def q_to_dict(q):
        if hasattr(q, "dict"):
            return q.dict()
        return {
            "id": getattr(q, "id", None),
            "stem": getattr(q, "stem", ""),
            "options": getattr(q, "options", []) or [],
            "answer": getattr(q, "answer", None),
            "explanation": getattr(q, "explanation", None),
            "difficulty": getattr(q, "difficulty", "medium"),
            "knowledge_points": getattr(q, "knowledge_points", []) or [],
            "question_type": getattr(q, "question_type", "short_answer"),
            "tags": getattr(q, "tags", []) or [],
        }

    questions_data = [q_to_dict(q) for q in qb.questions]

    return {
        "conversation_id": conversation_id,
        "question_count": len(questions_data),
        "questions": questions_data,
    }


@router.post(
    "/api/conversations/{conversation_id}/exercises/submissions"
)
async def submit_student_answers(
    conversation_id: str,
    studentName: str = Form(default="anonymous"),
    answers: str = Form(default=None),
    file: FUploadFile = FFile(default=None)
):
    """
    接收学生答卷（JSON answers 或上传的文件），并调用 Agent G 对答案进行评分。
    - studentName: 可选，学生姓名，默认为 'anonymous'
    - answers: 可选，JSON 字符串，格式 {"Q001": "答案", ...}
    - file: 可选，支持 PDF/DOCX/TXT 文件解析为答案（尝试解析 Qxxx: 答案 格式）
    返回 grading report JSON。
    """
    svc = ExerciseService()

    # 调试信息
    print(f"\n[DEBUG] ========== 批改请求 ==========")
    print(f"[DEBUG] conversation_id: {conversation_id}")
    print(f"[DEBUG] studentName: {studentName}")
    print(f"[DEBUG] answers: {answers}")
    print(f"[DEBUG] file: {file}")
    if file:
        print(f"[DEBUG] file.filename: {file.filename}")
        print(f"[DEBUG] file.content_type: {file.content_type}")

    answers_map = {}

    # 1) 优先解析 answers 字段（JSON 字符串）
    if answers:
        try:
            parsed = json.loads(answers)
            if isinstance(parsed, dict):
                answers_map = parsed
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"answers 字段必须为 JSON 字符串: {e}")

    # 2) 若没有 answers，则尝试解析上传的文件（支持 PDF/DOCX/TXT）
    # 检查文件是否真的存在：file 不为 None，且有 filename 且 filename 不为空字符串
    has_file = file is not None and hasattr(file, 'filename') and file.filename and file.filename.strip()
    print(f"[DEBUG] has_file check: file={file}, has filename={hasattr(file, 'filename') if file else False}, filename={file.filename if file and hasattr(file, 'filename') else 'N/A'}")
    
    if not answers_map and has_file:
        try:
            # 检查文件大小（50MB限制）
            content = await file.read()
            if not content or len(content) == 0:
                raise HTTPException(status_code=400, detail="上传的文件为空")
            if len(content) > 50 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")
            
            # 根据文件类型解析内容
            file_ext = Path(file.filename).suffix.lower() if file.filename else ''
            text = ""
            
            if file_ext == '.txt':
                # TXT 文件直接解码
                try:
                    text = content.decode('utf-8')
                except Exception:
                    text = content.decode('gbk', errors='ignore')
            
            elif file_ext == '.pdf':
                # PDF 文件解析
                from app.utils.pdf_parser import PDFParser
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    parser = PDFParser()
                    # 使用 extract_text 方法直接获取文本内容
                    text = parser.extract_text(tmp_path)
                    print(f"[DEBUG] PDF解析成功，文本长度: {len(text)}")
                    if not text or not text.strip():
                        print(f"[WARNING] PDF文件可能是扫描件（图片格式），无法提取文字")
                        raise HTTPException(
                            status_code=400, 
                            detail="PDF文件无法提取文字。如果是扫描件，请使用OCR工具转换后再上传，或者使用TXT格式手动输入答案。"
                        )
                    print(f"[DEBUG] PDF文本前200字符: {text[:200]}")
                except HTTPException:
                    raise
                except Exception as e:
                    print(f"[ERROR] PDF解析失败: {e}")
                    raise HTTPException(status_code=400, detail=f"PDF解析失败: {str(e)}")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            
            elif file_ext in ['.docx', '.doc']:
                # DOCX 文件解析
                print(f"[DEBUG] 开始解析 DOCX 文件: {file.filename}")
                import tempfile
                try:
                    from docx import Document
                except ImportError:
                    raise HTTPException(status_code=500, detail="缺少 python-docx 库，请安装: pip install python-docx")
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    doc = Document(tmp_path)
                    # 提取所有段落文本
                    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
                    text = '\n'.join(paragraphs)
                    print(f"[DEBUG] DOCX解析成功，段落数: {len(paragraphs)}, 文本长度: {len(text)}, 前200字符: {text[:200]}")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"不支持的文件格式: {file_ext}，仅支持 PDF、DOCX、TXT"
                )

            # 解析答案格式（支持多种格式）
            # 格式1: Q001: 答案 或 Q001. 答案 或 Q001) 答案
            pattern_q = re.compile(r"(Q\d{1,4})\s*[:：\.\)]\s*(.+)", re.I)  # 忽略大小写
            matches = pattern_q.findall(text)
            if matches:
                for qid, ans in matches:
                    answers_map[qid.upper()] = ans.strip()
                print(f"[DEBUG] 解析到 {len(answers_map)} 道题目答案（Q格式）")
            
            # 格式2: GEN_001: 答案 或 GEN_001. 答案（支持生成的题目ID格式）
            if not answers_map:
                pattern_gen = re.compile(r"(GEN_\d{1,4})\s*[:：\.\)]\s*(.+)", re.I)
                matches_gen = pattern_gen.findall(text)
                if matches_gen:
                    for qid, ans in matches_gen:
                        answers_map[qid.upper()] = ans.strip()
                    print(f"[DEBUG] 解析到 {len(answers_map)} 道题目答案（GEN格式）")
            
            # 格式3: 数字序号（1. 答案 或 1、答案 或 1) 答案）- 放宽匹配，允许行首有空白
            if not answers_map:
                pattern_n = re.compile(r"^\s*(\d{1,3})[\.、\)]\s*(.+)$", re.M)  # 允许行首空白
                matches2 = pattern_n.findall(text)
                if matches2:
                    for num, ans in matches2:
                        qid = f"Q{int(num):03d}"
                        answers_map[qid] = ans.strip()
                    print(f"[DEBUG] 解析到 {len(answers_map)} 道题目答案（数字格式）")
            
            # 格式4: 每行一个答案（无题号，按行序号匹配）
            if not answers_map:
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                if len(lines) > 0 and len(lines) <= 100:  # 合理的题目数量
                    print(f"[DEBUG] 尝试按行解析（共{len(lines)}行）")
                    for idx, line in enumerate(lines, 1):
                        # 排除明显的标题行
                        if not any(keyword in line for keyword in ['答案', '学生', '姓名', '班级', 'answer', 'student']):
                            qid = f"Q{idx:03d}"
                            answers_map[qid] = line
                    if answers_map:
                        print(f"[DEBUG] 按行解析到 {len(answers_map)} 道题目答案")
            
            if not answers_map:
                print(f"[DEBUG] 未能从文本中解析出答案")
                print(f"[DEBUG] 文本内容（前500字符）:\n{text[:500]}")

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"解析上传文件失败: {e}")

    if not answers_map:
        error_msg = "❌ 未能解析出答案数据。\n\n"
        error_msg += "📋 支持的答案格式（任选其一）：\n\n"
        error_msg += "格式1 - 使用生成的题目ID：\n"
        error_msg += "  GEN_001: 您的答案\n"
        error_msg += "  GEN_002: 您的答案\n\n"
        error_msg += "格式2 - 使用Q编号：\n"
        error_msg += "  Q001: 您的答案\n"
        error_msg += "  Q002: 您的答案\n\n"
        error_msg += "格式3 - 使用数字序号：\n"
        error_msg += "  1. 您的答案\n"
        error_msg += "  2. 您的答案\n\n"
        error_msg += "格式4 - 每行一个答案（无题号）：\n"
        error_msg += "  第一题的答案\n"
        error_msg += "  第二题的答案\n\n"
        error_msg += "💡 提示：\n"
        error_msg += "  • 推荐使用 TXT 格式以确保兼容性\n"
        error_msg += "  • PDF扫描件需先OCR转文字\n"
        error_msg += "  • 题号可使用中英文符号（: . 、）\n"
        error_msg += "  • 支持行首缩进或空格\n"
        print(f"[DEBUG] {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

    print(f"[DEBUG] 解析到的原始答案格式: {answers_map}")

    # 智能匹配题目ID：将 Q001 格式映射到实际题库的ID格式（如 GEN_001）
    try:
        from app.agents.database.question_bank_storage import load_question_bank
        qb = load_question_bank(f"{conversation_id}_generated")
        if qb and hasattr(qb, 'questions') and qb.questions:
            # 创建序号到实际ID的映射
            remapped_answers = {}
            questions_list = list(qb.questions)
            
            # 方案1: 尝试按序号匹配（Q001 -> 第1题）
            for key, ans in answers_map.items():
                # 提取数字序号
                num_match = re.search(r'(\d+)', key)
                if num_match:
                    idx = int(num_match.group(1)) - 1  # 转为0-based索引
                    if 0 <= idx < len(questions_list):
                        q = questions_list[idx]
                        actual_id = q.id if hasattr(q, 'id') else (q.get('id') if isinstance(q, dict) else None)
                        if actual_id:
                            remapped_answers[actual_id] = ans
                            print(f"[DEBUG] 映射 {key} -> {actual_id}: {ans[:50]}...")
                        else:
                            remapped_answers[key] = ans
                    else:
                        # 超出题目范围，保持原key
                        remapped_answers[key] = ans
                else:
                    remapped_answers[key] = ans
            
            answers_map = remapped_answers
            print(f"[DEBUG] 智能映射后的答案: {answers_map}")
    except Exception as e:
        print(f"[WARNING] 智能ID映射失败，使用原始ID: {e}")

    print(f"[DEBUG] 最终解析到的答案: {answers_map}")

    # 调用服务进行评分（在线程池中运行同步包装）
    try:
        report = await run_in_threadpool(svc.grade_submission, conversation_id, studentName, answers_map)
        return JSONResponse(content=report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评分失败: {e}")


@router.post(
    "/api/conversations/{conversation_id}/exercises/grade",
)
async def grade_generated_questions(conversation_id: str):
    """
    启动对已生成题库的 Agent G 批改流程（同步调用，可能较慢）。
    返回 quality_report（若存在）。
    """
    service = ExerciseService()
    try:
        # run in threadpool because grading may call asyncio.run and block
        report = await run_in_threadpool(service.grade_generated, conversation_id)
        if not report:
            raise HTTPException(status_code=500, detail="批改未返回报告")
        return JSONResponse(content=report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批改失败: {e}")


@router.get(
    "/api/conversations/{conversation_id}/exercises/grade/report"
)
async def get_grade_report(conversation_id: str):
    """
    返回最近一次批改报告（shared_state 或磁盘）。
    """
    # 先尝试 shared_state
    report = getattr(shared_state, "quality_report", None)
    if report and report.get("conversation_id") == conversation_id:
        return JSONResponse(content=report)

    # 再尝试从磁盘读取 report 文件（存在于保存的 graded question bank 同目录）
    try:
        # graded question bank filename is <conversation_id>_graded.json under data or configured storage
        from app.agents.database.question_bank_storage import find_saved_question_bank_path
        path = find_saved_question_bank_path(f"{conversation_id}_graded")
        if path:
            report_path = path.replace('.json', '_grade_report.json')
            if os.path.exists(report_path):
                with open(report_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return JSONResponse(content=data)
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="未找到批改报告")


@router.get(
    "/api/conversations/{conversation_id}/exercises/records"
)
async def get_student_records(conversation_id: str):
    """
    获取该会话下所有学生批改记录
    返回格式: {records: [{id, studentName, examName, score, maxScore, submitTime, details, recommendations}]}
    """
    service = ExerciseService()
    try:
        records = await run_in_threadpool(service.get_all_records, conversation_id)
        return JSONResponse(content={"records": records})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取记录失败: {e}")


@router.delete(
    "/api/conversations/{conversation_id}/exercises/records/{record_id}"
)
async def delete_student_record(conversation_id: str, record_id: str):
    """
    删除指定的学生批改记录
    """
    service = ExerciseService()
    try:
        await run_in_threadpool(service.delete_record, conversation_id, record_id)
        return JSONResponse(content={"message": "删除成功"})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.get(
    "/api/conversations/{conversation_id}/exercises/grading-report/download"
)
async def download_grading_pdf(conversation_id: str, pdf_path: str):
    """
    下载批改报告PDF
    """
    import app.config as config
    from pathlib import Path
    
    # 构建完整路径
    full_path = Path(config.settings.data_dir) / pdf_path
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="PDF文件不存在")
    
    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type="application/pdf"
    )


