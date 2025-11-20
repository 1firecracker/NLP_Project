"""样本试题服务，处理样本试题上传、解析、管理"""
import base64
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import UploadFile

import app.config as config
from app.utils.exercise_parser import ExerciseParser

from app.agents.quiz_graph import run_agent_chain, validate_outputs
from app.agents.database.question_bank_storage import load_question_bank
from app.agents.shared_state import shared_state
from app.agents.agent_g_grader import run_agent_g
from app.agents.agent_g_grader import run_grade_student_submission
from app.agents.agent_h_learning_advisor import run_agent_h


class ExerciseService:
    """样本试题服务"""
    
    def __init__(self):
        self.parser = ExerciseParser()
        self.exercises_dir = Path(config.settings.exercises_dir)
        self.exercises_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_conversation_samples_dir(self, conversation_id: str) -> Path:
        """获取对话的样本试题目录"""
        return self.exercises_dir / conversation_id / "samples"
    
    def _get_sample_dir(self, conversation_id: str, sample_id: str) -> Path:
        """获取样本试题目录"""
        return self._get_conversation_samples_dir(conversation_id) / sample_id
    
    def _get_metadata_file(self, conversation_id: str, sample_id: str) -> Path:
        """获取元数据文件路径"""
        return self._get_sample_dir(conversation_id, sample_id) / "metadata.json"
    
    def _validate_file(self, filename: str) -> tuple[bool, Optional[str]]:
        """验证文件类型"""
        file_ext = Path(filename).suffix.lower().lstrip('.')
        if file_ext not in config.settings.exercise_allowed_extensions:
            return False, f"不支持的文件类型: {file_ext}，仅支持 {', '.join(config.settings.exercise_allowed_extensions)}"
        return True, None
    
    async def _check_file_size(self, file_content: bytes) -> tuple[bool, Optional[str]]:
        """检查文件大小"""
        file_size = len(file_content)
        if file_size > config.settings.max_file_size:
            return False, f"文件大小 {file_size / 1024 / 1024:.2f}MB 超过限制 {config.settings.max_file_size / 1024 / 1024}MB"
        return True, None
    
    async def upload_samples(
        self,
        conversation_id: str,
        files: List[UploadFile]
    ) -> Dict:
        """上传样本试题
        
        Args:
            conversation_id: 对话ID
            files: 文件列表
            
        Returns:
            上传结果字典
        """
        if not files:
            raise ValueError("至少需要上传一个文件")
        
        # 检查样本数量限制
        existing_samples = self.list_samples(conversation_id)
        if len(existing_samples) + len(files) > config.settings.max_samples_per_conversation:
            raise ValueError(
                f"当前已有 {len(existing_samples)} 个样本，再上传 {len(files)} 个将超过限制 "
                f"({config.settings.max_samples_per_conversation} 个)"
            )
        
        uploaded_samples = []
        samples_dir = self._get_conversation_samples_dir(conversation_id)
        samples_dir.mkdir(parents=True, exist_ok=True)
        
        for file in files:
            # 验证文件类型
            is_valid, error_msg = self._validate_file(file.filename)
            if not is_valid:
                raise ValueError(error_msg)
            
            # 读取文件内容
            file_content = await file.read()
            
            # 验证文件大小
            is_valid, error_msg = await self._check_file_size(file_content)
            if not is_valid:
                raise ValueError(error_msg)
            
            # 生成样本ID（使用文件名，去除扩展名）
            original_path = Path(file.filename)
            sample_id = original_path.stem
            
            # 如果已存在同名样本，添加后缀
            sample_dir = samples_dir / sample_id
            counter = 1
            while sample_dir.exists():
                sample_id = f"{original_path.stem}_{counter}"
                sample_dir = samples_dir / sample_id
                counter += 1
            
            # 创建样本目录
            sample_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存原始文件
            original_file_path = sample_dir / file.filename
            with open(original_file_path, 'wb') as f:
                f.write(file_content)
            
            # 创建初始元数据（状态为 pending）
            upload_time = datetime.utcnow().isoformat() + "Z"
            initial_metadata = {
                "sample_id": sample_id,
                "conversation_id": conversation_id,
                "original_filename": file.filename,
                "original_file_path": str(original_file_path.relative_to(sample_dir)),
                "file_type": Path(file.filename).suffix.lower().lstrip('.'),
                "file_size": len(file_content),
                "upload_time": upload_time,
                "status": "pending",
                "parse_start_time": None,
                "parse_end_time": None,
                "error": None
            }
            
            # 保存初始元数据
            metadata_file = self._get_metadata_file(conversation_id, sample_id)
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(initial_metadata, f, ensure_ascii=False, indent=2)
            
            uploaded_samples.append({
                "sample_id": sample_id,
                "filename": file.filename,
                "file_size": len(file_content),
                "file_type": initial_metadata["file_type"],
                "status": "pending",
                "upload_time": upload_time
            })
        
        return {
            "conversation_id": conversation_id,
            "uploaded_samples": uploaded_samples,
            "total_samples": len(uploaded_samples)
        }
    
    def _parse_sample_async(
        self,
        conversation_id: str,
        sample_id: str,
        original_file_path: Path
    ):
        """异步解析样本文件（后台任务）
        
        Args:
            conversation_id: 对话ID
            sample_id: 样本ID
            original_file_path: 原始文件路径
        """
        import logging
        logger = logging.getLogger(__name__)
        
        metadata_file = self._get_metadata_file(conversation_id, sample_id)
        sample_dir = self._get_sample_dir(conversation_id, sample_id)
        
        try:
            # 更新状态为 processing
            self._update_parse_status(
                conversation_id, sample_id,
                status="processing",
                parse_start_time=datetime.utcnow().isoformat() + "Z"
            )
            
            # 使用ExerciseParser解析文件
            content = self.parser.extract_content(
                str(original_file_path),
                save_to=None,
                conversation_id=conversation_id,
                document_id=sample_id,
            )
            
            # 直接保存文本和图片到 sample_dir
            text_file = sample_dir / "text.txt"
            text_file.write_text(content["text"], encoding='utf-8')
            
            # 保存图片
            images_dir = sample_dir / "images"
            images_dir.mkdir(exist_ok=True)
            
            saved_images = []
            for i, img in enumerate(content.get("images", [])):
                try:
                    # 情况1：有 image_base64（本地解析，如 PyMuPDF）
                    if img.get("image_base64"):
                        img_data = base64.b64decode(img["image_base64"])
                        img_index = img.get("image_index", i + 1)
                        img_format = img.get("image_format", "png")
                        page_number = img.get("page_number", 1)
                        img_file = images_dir / f"page_{page_number}_img_{img_index}.{img_format}"
                        img_file.write_bytes(img_data)
                        
                        logger.info(f"保存图片成功: {img_file.name}, 大小: {len(img_data)} 字节")
                        
                        saved_images.append({
                            "page_number": page_number,
                            "image_index": img_index,
                            "file_path": f"images/{img_file.name}",
                            "image_format": img_format,
                            "width": img.get("width", 0),
                            "height": img.get("height", 0)
                        })
                    # 情况2：只有 file_path（Gitee OCR，图片已保存）
                    elif img.get("file_path"):
                        file_path = img.get("file_path")
                        # file_path 可能是相对路径（如 "images/image_4_1.jpg"）或绝对路径
                        if file_path.startswith("images/"):
                            # 相对路径，检查文件是否存在
                            img_file = sample_dir / file_path
                            if img_file.exists():
                                logger.info(f"使用已存在的图片: {file_path}")
                                saved_images.append({
                                    "page_number": img.get("page_number"),
                                    "image_index": img.get("image_index", i + 1),
                                    "file_path": file_path,
                                    "image_format": img.get("image_format", img_file.suffix.lstrip('.')),
                                    "width": img.get("width", 0),
                                    "height": img.get("height", 0)
                                })
                            else:
                                logger.warning(f"图片文件不存在: {file_path}")
                        else:
                            # 绝对路径或其他格式，直接使用
                            logger.info(f"使用图片路径: {file_path}")
                            saved_images.append({
                                "page_number": img.get("page_number"),
                                "image_index": img.get("image_index", i + 1),
                                "file_path": file_path,
                                "image_format": img.get("image_format", "unknown"),
                                "width": img.get("width", 0),
                                "height": img.get("height", 0)
                            })
                    else:
                        logger.warning(f"图片 {i+1} 既没有 base64 数据也没有 file_path，跳过")
                        continue
                except Exception as e:
                    logger.error(f"处理图片 {i+1} 失败: {e}", exc_info=True)
                    continue
            
            # 更新元数据（解析成功）
            parse_end_time = datetime.utcnow().isoformat() + "Z"
            self._update_parse_status(
                conversation_id, sample_id,
                status="completed",
                parse_end_time=parse_end_time,
                file_type=content["file_type"],
                text_length=len(content["text"]),
                image_count=len(saved_images),
                images=saved_images
            )
            
            logger.info(f"样本解析完成: sample_id={sample_id}, image_count={len(saved_images)}")
            
        except Exception as e:
            # 更新状态为 failed
            error_msg = str(e)
            logger.error(f"样本解析失败: sample_id={sample_id}, 错误: {error_msg}", exc_info=True)
            self._update_parse_status(
                conversation_id, sample_id,
                status="failed",
                parse_end_time=datetime.utcnow().isoformat() + "Z",
                error=error_msg
            )
    
    def _update_parse_status(
        self,
        conversation_id: str,
        sample_id: str,
        status: str,
        parse_start_time: Optional[str] = None,
        parse_end_time: Optional[str] = None,
        error: Optional[str] = None,
        file_type: Optional[str] = None,
        text_length: Optional[int] = None,
        image_count: Optional[int] = None,
        images: Optional[List[Dict]] = None
    ):
        """更新解析状态
        
        Args:
            conversation_id: 对话ID
            sample_id: 样本ID
            status: 状态 (pending/processing/completed/failed)
            parse_start_time: 解析开始时间
            parse_end_time: 解析结束时间
            error: 错误信息
            file_type: 文件类型
            text_length: 文本长度
            image_count: 图片数量
            images: 图片列表
        """
        metadata_file = self._get_metadata_file(conversation_id, sample_id)
        
        if not metadata_file.exists():
            return
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            metadata["status"] = status
            if parse_start_time is not None:
                metadata["parse_start_time"] = parse_start_time
            if parse_end_time is not None:
                metadata["parse_end_time"] = parse_end_time
            if error is not None:
                metadata["error"] = error
            if file_type is not None:
                metadata["file_type"] = file_type
            if text_length is not None:
                metadata["text_length"] = text_length
                metadata["text_file"] = "text.txt"
            if image_count is not None:
                metadata["image_count"] = image_count
            if images is not None:
                metadata["images"] = images
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"更新解析状态失败: {e}", exc_info=True)
    
    def list_samples(self, conversation_id: str) -> List[Dict]:
        """获取样本试题列表
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            样本试题列表
        """
        samples_dir = self._get_conversation_samples_dir(conversation_id)
        if not samples_dir.exists():
            return []
        
        samples = []
        for sample_dir in samples_dir.iterdir():
            if not sample_dir.is_dir():
                continue
            
            metadata_file = sample_dir / "metadata.json"
            if not metadata_file.exists():
                continue
            
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    
                    # 获取图片数量：优先使用 metadata 中的值，如果为 0 则从文件系统检查
                    image_count = metadata.get("image_count", 0)
                    if image_count == 0:
                        # 检查 images 数组
                        images_list = metadata.get("images", [])
                        if images_list:
                            image_count = len(images_list)
                        else:
                            # 从文件系统检查实际图片文件数量
                            images_dir = sample_dir / "images"
                            if images_dir.exists() and images_dir.is_dir():
                                image_files = [f for f in images_dir.iterdir() if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']]
                                image_count = len(image_files)
                    
                    samples.append({
                        "sample_id": metadata.get("sample_id", sample_dir.name),
                        "filename": metadata.get("original_filename", metadata.get("filename", sample_dir.name)),
                        "file_type": metadata.get("file_type", "unknown"),
                        "file_size": metadata.get("file_size", 0),
                        "text_length": metadata.get("text_length", 0),
                        "image_count": image_count,
                        "upload_time": metadata.get("upload_time", ""),
                        "status": metadata.get("status", "unknown")
                    })
            except Exception:
                continue
        
        # 按上传时间倒序排列
        samples.sort(key=lambda x: x.get("upload_time", ""), reverse=True)
        return samples
    
    def get_sample(self, conversation_id: str, sample_id: str) -> Optional[Dict]:
        """获取样本试题详情
        
        Args:
            conversation_id: 对话ID
            sample_id: 样本ID
            
        Returns:
            样本试题详情，如果不存在返回None
        """
        metadata_file = self._get_metadata_file(conversation_id, sample_id)
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # 确保包含必要字段（兼容旧格式）
            if "sample_id" not in metadata:
                metadata["sample_id"] = sample_id
            if "conversation_id" not in metadata:
                metadata["conversation_id"] = conversation_id
            if "filename" not in metadata:
                # 兼容旧格式：file_id 或 original_filename
                metadata["filename"] = metadata.get("original_filename", metadata.get("file_id", sample_id))
            if "original_filename" not in metadata:
                metadata["original_filename"] = metadata.get("filename", sample_id)
            
            # 确保必需字段有默认值（必须在读取文本前设置）
            metadata.setdefault("file_size", 0)
            metadata.setdefault("upload_time", "")
            metadata.setdefault("images", [])
            
            # 读取文本内容
            sample_dir = self._get_sample_dir(conversation_id, sample_id)
            text_file = sample_dir / metadata.get("text_file", "text.txt")
            text_content = ""
            
            # 如果文件不存在，尝试在子目录中查找（兼容旧的保存结构）
            if not text_file.exists():
                # 检查是否有子目录（旧格式：sample_dir/sample_id/text.txt）
                sub_dir = sample_dir / sample_id
                if sub_dir.exists() and sub_dir.is_dir():
                    alt_text_file = sub_dir / metadata.get("text_file", "text.txt")
                    if alt_text_file.exists():
                        text_file = alt_text_file
            
            if text_file.exists():
                try:
                    with open(text_file, 'r', encoding='utf-8') as f:
                        text_content = f.read()
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"读取文本文件失败: {text_file}, 错误: {e}")
                    text_content = ""
            
            metadata["text_content"] = text_content
            return metadata
        except Exception:
            return None
    
    def delete_sample(self, conversation_id: str, sample_id: str) -> bool:
        """删除样本试题
        
        Args:
            conversation_id: 对话ID
            sample_id: 样本ID
            
        Returns:
            是否删除成功
        """
        sample_dir = self._get_sample_dir(conversation_id, sample_id)
        if not sample_dir.exists():
            return False
        
        try:
            shutil.rmtree(sample_dir)
            return True
        except Exception:
            return False
    
    def get_sample_text(self, conversation_id: str, sample_id: str) -> Optional[str]:
        """获取样本试题文本内容
        
        Args:
            conversation_id: 对话ID
            sample_id: 样本ID
            
        Returns:
            文本内容，如果不存在返回None
        """
        sample = self.get_sample(conversation_id, sample_id)
        if not sample:
            return None
        return sample.get("text_content", "")

    def _find_any_completed_conversation(self) -> Optional[str]:
        """
        在 exercises 根目录下自动寻找“至少有一个解析完成样本”的 conversation_id，
        返回最近上传的那个 conversation_id；如果找不到则返回 None。
        """
        if not self.exercises_dir.exists():
            return None

        candidates: list[tuple[str, str]] = []  # (latest_upload_time, conversation_id)

        for conv_dir in self.exercises_dir.iterdir():
            if not conv_dir.is_dir():
                continue
            conv_id = conv_dir.name
            samples = self.list_samples(conv_id)
            # 只要有一个状态为 completed 的样本，就认为这个会话可用
            completed = [s for s in samples if s.get("status") == "completed"]
            if not completed:
                continue
            # 找这个会话里最新的上传时间
            latest_time = max(s.get("upload_time", "") for s in completed)
            candidates.append((latest_time, conv_id))

        if not candidates:
            return None

        # 按上传时间逆序排序，取最新的那个 conversation_id
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def generate_questions(self, conversation_id: str, up_to: str = "F") -> Dict:
        """
        基于当前/最近一次已上传并解析完成的样本试题，
        启动整条出题 Agent 链（A~F），并返回生成结果概要。

        注意：
        - 不再强依赖前端传入的 conversation_id；
        - 如果当前 conversation 下没有样本，会自动在所有会话中寻找最近的一个。
        """
        # 先尝试用“当前” conversation_id
        effective_id = conversation_id
        samples = self.list_samples(conversation_id)

        # 1) 如果当前会话根本没有样本，或者没有任何 completed 的样本，就自动兜底
        if (not samples) or (not any(s.get("status") == "completed" for s in samples)):
            auto_conv = self._find_any_completed_conversation()
            if auto_conv is None:
                # 真·一个样本都没解析成功过
                raise ValueError("找不到任何已上传且解析完成的样本试卷，请先在前端上传并等待解析完成。")
            effective_id = auto_conv
            samples = self.list_samples(effective_id)

        # 打个日志（方便以后你调试）
        print(f"[AgentPipeline] 使用会话 {effective_id} 作为出题输入（找到 {len(samples)} 个样本）")

        # 2) 启动 Agent 链
        #    Agent A 会在 run_agent_a 中使用 "__AUTO__" 自动扫描 backend/uploads/exercises 下的 text.txt
        run_agent_chain(effective_id, ["__AUTO__"], up_to=up_to)

        # 3) 管道健康检查（A~F 哪些成功/缺失）
        pipeline_status = validate_outputs(effective_id)

        # 4) 载入生成后的题库（<conversation_id>_generated）
        generated_id = f"{effective_id}_generated"
        qb_generated = load_question_bank(generated_id)
        if qb_generated is None or not getattr(qb_generated, "questions", None):
            raise ValueError("题目生成流程已完成，但未找到生成题库文件。")

        question_count = len(qb_generated.questions)

        # 5) 拿到 Agent F 的质量报告（如果有的话）
        quality_report = getattr(shared_state, "quality_report", None)

        return {
            "conversation_id": effective_id,
            "generated_conversation_id": generated_id,
            "question_count": question_count,
            "pipeline_status": pipeline_status,
            "quality_report": quality_report,
        }

    def grade_generated(self, conversation_id: str):
        """
        对已经生成的试题（conversation_id_generated）运行 Agent G 批改器。
        返回 quality_report。
        """
        # 优先尝试传入的会话，如果不存在则尝试自动查找
        generated_id = f"{conversation_id}_generated"
        qb = load_question_bank(generated_id)
        if qb is None or not getattr(qb, "questions", None):
            # 尝试寻找最近一个生成过的会话
            auto_conv = self._find_any_completed_conversation()
            if auto_conv:
                generated_id = f"{auto_conv}_generated"
                qb = load_question_bank(generated_id)

        if qb is None or not getattr(qb, "questions", None):
            raise ValueError("未找到可批改的生成题库，请先运行生成流程。")

        # 调用 Agent G（同步包装）
        report = run_agent_g(generated_id.replace("_generated", ""))
        return report

    def grade_submission(self, conversation_id: str, student_name: str, answers_map: dict):
        """
        使用 Agent G 对学生提交的 answers_map（{questionId: answer}）进行评分。
        然后调用 Agent H 生成学习诊断与建议。
        最后生成PDF报告。
        """
        # Call Agent G for grading (synchronous wrapper)
        report = run_grade_student_submission(conversation_id, student_name, answers_map)
        
        # Add timestamp for record tracking
        timestamp = datetime.now().isoformat()
        report["timestamp"] = timestamp
        
        # Call Agent H for learning advice
        try:
            h_report = run_agent_h(report, conversation_id, student_name)
            # Merge Agent H results into the grading report
            report["learning_advice"] = h_report
            # Enhance recommendations with Agent H's priority topics
            if h_report.get("learning_plan", {}).get("priority_topics"):
                priority_topics = h_report["learning_plan"]["priority_topics"]
                for pt in priority_topics:
                    report["recommendations"].append(
                        f"优先学习：{pt['topic']} - {pt['reason']}"
                    )
        except Exception as e:
            print(f"[⚠️ Agent H 执行失败，跳过学习建议生成] {e}")
            report["learning_advice"] = None
        
        # Generate PDF report
        try:
            pdf_path = self._generate_grading_pdf(conversation_id, student_name, report)
            report["pdf_path"] = pdf_path
            print(f"[✅ PDF报告已生成] {pdf_path}")
        except Exception as e:
            print(f"[⚠️ PDF生成失败] {e}")
            report["pdf_path"] = None
        
        return report

    def _generate_grading_pdf(self, conversation_id: str, student_name: str, report: dict) -> str:
        """
        生成批改报告PDF
        返回PDF文件的相对路径
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.units import cm
        
        # 创建PDF目录
        pdf_dir = Path(config.settings.data_dir) / conversation_id / "grading_reports"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成PDF文件名
        timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
        pdf_filename = f"grading_{student_name}_{timestamp_str}.pdf"
        pdf_path = pdf_dir / pdf_filename
        
        # 注册中文字体（使用系统字体）
        try:
            font_path = "C:/Windows/Fonts/msyh.ttc"  # 微软雅黑
            pdfmetrics.registerFont(TTFont('msyh', font_path))
            font_name = 'msyh'
        except:
            font_name = 'Helvetica'  # 回退到默认字体
        
        # 创建PDF文档
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        elements = []
        
        # 样式
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=font_name,
            fontSize=20,
            textColor=colors.HexColor('#1a73e8'),
            spaceAfter=20,
            alignment=1  # 居中
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=font_name,
            fontSize=14,
            textColor=colors.HexColor('#333333'),
            spaceAfter=12
        )
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontName=font_name,
            fontSize=10,
            textColor=colors.HexColor('#666666')
        )
        
        # 标题
        elements.append(Paragraph("试卷批改报告", title_style))
        elements.append(Spacer(1, 0.5*cm))
        
        # 基本信息
        info_data = [
            ["学生姓名", student_name or "匿名"],
            ["批改时间", report.get("graded_at", "")[:19].replace("T", " ")],
            ["总题数", str(report.get("question_count", 0))],
            ["平均分", f"{report.get('average_score', 0):.1f} / 100"]
        ]
        info_table = Table(info_data, colWidths=[4*cm, 12*cm])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1a73e8')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f7ff')),
            ('PADDING', (0, 0), (-1, -1), 8)
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.8*cm))
        
        # 题目批改详情
        elements.append(Paragraph("题目批改详情", heading_style))
        question_data = [["题号", "题型", "得分", "反馈"]]
        for item in report.get("per_question", []):
            question_data.append([
                item.get("id", ""),
                item.get("question_type", ""),
                f"{item.get('score', 0)}/100",
                item.get("feedback", "")[:50] + "..." if len(item.get("feedback", "")) > 50 else item.get("feedback", "")
            ])
        
        question_table = Table(question_data, colWidths=[2*cm, 3*cm, 2.5*cm, 8.5*cm])
        question_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a73e8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        elements.append(question_table)
        elements.append(Spacer(1, 0.8*cm))
        
        # 学习建议
        if report.get("recommendations"):
            elements.append(Paragraph("学习建议", heading_style))
            for rec in report.get("recommendations", []):
                elements.append(Paragraph(f"• {rec}", body_style))
                elements.append(Spacer(1, 0.2*cm))
        
        # 生成PDF
        doc.build(elements)
        
        # 返回相对路径（相对于data目录）
        return f"{conversation_id}/grading_reports/{pdf_filename}"

    def get_all_records(self, conversation_id: str) -> List[Dict]:
        """
        获取指定会话下所有学生的批改记录
        从 data/<conversation_id>/submissions/ 目录读取所有 JSON 文件
        """
        submissions_dir = Path(config.settings.data_dir) / conversation_id / "submissions"
        
        if not submissions_dir.exists():
            return []
        
        records = []
        for submission_file in submissions_dir.glob("*.json"):
            try:
                with open(submission_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 提取关键信息
                    # 处理时间戳：兼容 timestamp 和 graded_at 字段
                    timestamp = data.get("timestamp") or data.get("graded_at")
                    if isinstance(timestamp, str) and timestamp:
                        # ISO格式转时间戳
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            submit_time = int(dt.timestamp() * 1000)
                        except:
                            submit_time = int(submission_file.stat().st_mtime * 1000)
                    elif isinstance(timestamp, (int, float)):
                        submit_time = int(timestamp)
                    else:
                        # 使用文件修改时间
                        submit_time = int(submission_file.stat().st_mtime * 1000)
                    
                    record = {
                        "id": submission_file.stem,  # 文件名作为记录ID
                        "studentName": data.get("student_name", "未知学生"),
                        "examName": f"试卷批改",
                        "score": round(data.get("average_score", 0)),
                        "maxScore": 100,
                        "submitTime": submit_time,
                        "pdfPath": data.get("pdf_path", None),  # PDF报告路径
                        "details": data.get("per_question", []),
                        "recommendations": data.get("recommendations", []),
                        "knowledgeAnalysis": data.get("knowledgeAnalysis", {}),
                        "learningAdvice": data.get("learning_advice", None)
                    }
                    print(f"[DEBUG] 读取记录: {record['studentName']}, 分数: {record['score']}, 时间: {submit_time}")
                    records.append(record)
            except Exception as e:
                print(f"[⚠️ 读取记录文件失败] {submission_file}: {e}")
                continue
        
        # 按提交时间降序排序
        records.sort(key=lambda x: x.get("submitTime", 0), reverse=True)
        print(f"[DEBUG] 共找到 {len(records)} 条记录")
        for r in records:
            print(f"  - {r['studentName']}: {r['score']}分, 时间:{r['submitTime']}")
        return records

    def delete_record(self, conversation_id: str, record_id: str):
        """
        删除指定的学生批改记录
        同时删除 submissions/、learning_advice/ 和 grading_reports/ 目录下的相关文件
        """
        # 读取记录文件获取PDF路径
        submission_file = Path(config.settings.data_dir) / conversation_id / "submissions" / f"{record_id}.json"
        pdf_path_to_delete = None
        
        if submission_file.exists():
            try:
                with open(submission_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    pdf_path_to_delete = data.get("pdf_path")
            except:
                pass
            
            # 删除批改记录文件
            submission_file.unlink()
        else:
            raise ValueError(f"未找到记录: {record_id}")
        
        # 删除学习建议文件（如果存在）
        advice_file = Path(config.settings.data_dir) / conversation_id / "learning_advice" / f"{record_id}.json"
        if advice_file.exists():
            advice_file.unlink()
        
        # 删除PDF文件（如果存在）
        if pdf_path_to_delete:
            pdf_file = Path(config.settings.data_dir) / pdf_path_to_delete
            if pdf_file.exists():
                pdf_file.unlink()
                print(f"[✅ 删除PDF报告] {pdf_file}")
        
        print(f"[✅ 删除记录成功] {record_id}")




