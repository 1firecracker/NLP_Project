# -*- coding: utf-8 -*-
# backend/app/models/quiz_models.py
# ===========================================================
# 说明：
# 本文件定义所有出题系统中使用的数据模型（Pydantic）。
# 它不需要任何训练，仅用于数据结构定义与校验。
# ===========================================================

from pydantic import BaseModel, Field
from typing import List, Dict, Optional


# -----------------------------
# 子问题结构
# -----------------------------
class SubQuestion(BaseModel):
    """子问题的数据结构"""
    label: str                                      # 子问标记（a/b/i/ii 等）
    stem: str                                       # 子问题干
    score: int = 0                                  # 子问分值
    question_type: Optional[str] = "short_answer"   # 子问题型
    sub_questions: List["SubQuestion"] = []         # 嵌套子问题


# -----------------------------
# 单道题目结构
# -----------------------------
class Question(BaseModel):
    """单道题目的数据结构"""
    id: str
    stem: str                                       # 题干
    options: Optional[List[str]] = None             # 选项（非选择题可为空）
    answer: str                                     # 正确答案
    explanation: Optional[str] = None               # 解析或参考答案
    difficulty: Optional[str] = "medium"            # 难度：easy / medium / hard
    knowledge_points: List[str] = []                # 对应知识点
    question_type: Optional[str] = "single_choice"  # 题型：单选、简答、计算等
    tags: Optional[List[str]] = []                  # 附加标签（章节、关键词等）
    sub_questions: List[SubQuestion] = []           # 子问题列表


# -----------------------------
# 题库（Agent A 输出）
# -----------------------------
class QuestionBank(BaseModel):
    """题库集合"""
    questions: List[Question]
    source_docs: Optional[List[str]] = []           # 来源文档（可关联已上传的资料文件ID）


# -----------------------------
# 知识点覆盖率统计（Agent B 输出）
# -----------------------------
class KnowledgePointStats(BaseModel):
    """知识点覆盖率与薄弱知识点分析结果"""
    stats: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="结构：{'知识点名': {'count':出现次数, 'coverage':覆盖率(0-1)}}"
    )


# -----------------------------
# 题型分布统计（Agent C 输出）
# -----------------------------
class QuestionTypeStats(BaseModel):
    """题型统计与分布比例"""
    stats: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="结构：{'题型名': {'count':数量, 'ratio':比例(0-1)}}"
    )


# -----------------------------
# 样例试卷结构（已废弃，原 Agent D 输出，现由 Agent E 内部处理）
# -----------------------------
class SampleExam(BaseModel):
    """样例试卷解析结果"""
    title: Optional[str] = None
    question_count: Optional[int] = 0
    type_distribution: Dict[str, float] = {}         # {"single_choice":0.6, "fill_blank":0.2, "short_answer":0.2}
    difficulty_distribution: Dict[str, float] = {}   # {"easy":0.5, "medium":0.3, "hard":0.2}
    section_order: List[str] = []                    # ["单选题", "填空题", "简答题"]
    average_words_per_question: Optional[float] = 0.0


# -----------------------------
# 模拟生成题集（Agent E 输出）
# -----------------------------
class GeneratedQuestions(BaseModel):
    """生成的新题集合"""
    questions: List[Question]


# -----------------------------
# 最终试卷结构（Agent F 输出）
# -----------------------------
class ExamPaper(BaseModel):
    """完整模拟试卷"""
    paper_id: str
    title: str
    questions: List[Question]
    meta: Dict[str, str] = Field(default_factory=dict)  # 题型比例、知识点覆盖率等信息
    mode: Optional[str] = "auto"                        # 出题模式：auto / sample_based


# -----------------------------
# 质量检测报告（Agent F 输出）
# -----------------------------
class QualityReport(BaseModel):
    """试卷质量检测结果"""
    duplicate_rate: float
    balance_ok: bool
    notes: Optional[str] = None                         # 额外说明（如“题型比例不完全符合样例分布”）


# -----------------------------
# 出题配置（前端传入）
# -----------------------------
class ExamConfig(BaseModel):
    """出题配置，由前端传入"""
    topic: str                                          # 出题主题，如 “机器学习基础”
    target_count: int = 10                              # 目标题量
    type_distribution: Optional[Dict[str, float]] = None  # {"single_choice":0.6, "short_answer":0.4}
    difficulty_curve: Optional[List[str]] = ["easy", "medium", "hard"]
    use_sample_exam: bool = False                       # 是否启用样例驱动模式
    sample_exam_path: Optional[str] = None              # 样例试卷路径（如果启用）
