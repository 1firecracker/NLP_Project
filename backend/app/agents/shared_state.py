# -*- coding: utf-8 -*-
# ===========================================================
# 文件：backend/app/agents/shared_state.py
# 功能：多 Agent 出题系统的共享状态池（核心内存总线）
# 说明：
#   所有 Agent（A~F）都通过此模块共享数据：
#   - 题库（A 输出）
#   - 知识点覆盖（B 输出）
#   - 题型统计（C 输出）
#   - 样例试卷结构（D 输出，可选）
#   - 生成题目（E 输出）
#   - 最终试卷与报告（F 输出）
# ===========================================================

from typing import Optional
from app.agents.models.quiz_models import (
    QuestionBank,
    KnowledgePointStats,
    QuestionTypeStats,
    SampleExam,
    GeneratedQuestions,
    ExamPaper,
    QualityReport,
)


class SharedState:
    """
    全局共享状态类。
    每个 conversation（会话）对应一个 SharedState 实例，
    存储各阶段中间结果，实现多 Agent 间数据交互。
    """

    def __init__(self):
        # 各阶段输出对象
        self.question_bank: Optional[QuestionBank] = None
        self.knowledge_point_stats: Optional[KnowledgePointStats] = None
        self.question_type_stats: Optional[QuestionTypeStats] = None
        self.sample_exam_stats: Optional[SampleExam] = None
        self.generated_questions: Optional[GeneratedQuestions] = None
        self.exam_paper: Optional[ExamPaper] = None
        self.quality_report: Optional[QualityReport] = None
        
        # 新增：存储原始文本内容，供 Agent E 使用
        self.source_text: Optional[str] = None
        self.generated_exam: Optional[QuestionBank] = None
        self.distribution_model: Optional[dict] = None

    # ---------------------------------------------------------
    # 工具方法
    # ---------------------------------------------------------
    def reset(self):
        """重置共享状态（通常在开始新出题流程前调用）"""
        self.__init__()

    def snapshot(self) -> dict:
        """
        生成当前状态快照（转 JSON 用）
        用于前端调试或存盘。
        """
        return {
            "question_bank": (
                self.question_bank.model_dump() if self.question_bank else None
            ),
            "knowledge_point_stats": (
                self.knowledge_point_stats.model_dump()
                if self.knowledge_point_stats
                else None
            ),
            "question_type_stats": (
                self.question_type_stats.model_dump()
                if self.question_type_stats
                else None
            ),
            "sample_exam_stats": (
                self.sample_exam_stats.model_dump()
                if self.sample_exam_stats
                else None
            ),
            "generated_questions": (
                self.generated_questions.model_dump()
                if self.generated_questions
                else None
            ),
            "exam_paper": (
                self.exam_paper.model_dump() if self.exam_paper else None
            ),
            "quality_report": (
                self.quality_report.model_dump() if self.quality_report else None
            ),
        }

    def summary(self) -> str:
        """简要打印当前状态信息（用于日志调试）"""
        return (
            f"📘 SharedState Summary:\n"
            f" - QuestionBank: {'✅' if self.question_bank else '❌'}\n"
            f" - KnowledgePointStats: {'✅' if self.knowledge_point_stats else '❌'}\n"
            f" - QuestionTypeStats: {'✅' if self.question_type_stats else '❌'}\n"
            f" - SampleExam: {'✅' if self.sample_exam_stats else '❌'}\n"
            f" - GeneratedQuestions: {'✅' if self.generated_questions else '❌'}\n"
            f" - ExamPaper: {'✅' if self.exam_paper else '❌'}\n"
            f" - QualityReport: {'✅' if self.quality_report else '❌'}"
        )


# ---------------------------------------------------------
# 全局实例（单例）
# ---------------------------------------------------------
shared_state = SharedState()
