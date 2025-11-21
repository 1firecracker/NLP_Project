# 临时补丁文件 - 添加清除缓存功能和改进生成逻辑
# 将此代码合并到 exercise_service.py 的 ExerciseService 类中

def _clear_generated_cache(self, conversation_id: str):
    """
    清除指定会话的生成题库缓存（磁盘文件和内存状态）
    """
    import os
    from app.agents.database.question_bank_storage import BASE_DATA_DIR
    from app.agents.shared_state import shared_state
    import shutil
    
    # 清除内存缓存
    shared_state.reset()
    
    # 清除磁盘文件（_generated, _corrected, _graded）
    suffixes = ['_generated', '_corrected', '_graded']
    for suffix in suffixes:
        cache_id = f"{conversation_id}{suffix}"
        cache_dir = os.path.join(BASE_DATA_DIR, cache_id)
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                print(f"[🗑️ 已清除缓存] {cache_dir}")
            except Exception as e:
                print(f"[⚠️ 清除缓存失败] {cache_dir}: {e}")


# 替换原有的 generate_questions 方法
def generate_questions_NEW(self, conversation_id: str, up_to: str = "F") -> Dict:
    """
    基于当前会话已上传并解析完成的样本试题，
    启动整条出题 Agent 链（A~F），并返回生成结果概要。

    改进点：
    - 严格使用当前 conversation_id，不再自动兜底到其他会话
    - 每次生成前清除旧缓存，确保生成新题目
    - 更明确的错误提示
    """
    from app.agents.quiz_graph import run_agent_chain, validate_outputs
    from app.agents.database.question_bank_storage import load_question_bank
    from app.agents.shared_state import shared_state
    
    # 只使用当前 conversation_id，不再自动查找其他会话
    effective_id = conversation_id
    samples = self.list_samples(conversation_id)

    # 检查当前会话是否有已完成的样本
    if not samples:
        raise ValueError(
            f"当前会话 [{conversation_id}] 未找到任何样本试卷。\n"
            "请先在【样本试卷】模块上传 PDF/DOCX/TXT 文件，并等待解析完成后再生成试题。"
        )
    
    completed_samples = [s for s in samples if s.get("status") == "completed"]
    if not completed_samples:
        pending_count = len([s for s in samples if s.get("status") == "pending"])
        if pending_count > 0:
            raise ValueError(
                f"当前会话有 {pending_count} 个样本正在解析中，请稍等片刻后再生成试题。"
            )
        else:
            raise ValueError(
                f"当前会话的样本解析失败。请重新上传样本试卷或检查文件格式。"
            )

    # 清除旧缓存（确保生成新题目）
    print(f"[🔄 清除旧缓存] 会话 {effective_id}")
    self._clear_generated_cache(effective_id)
    
    print(f"[AgentPipeline] 使用会话 {effective_id} 生成新题目（找到 {len(completed_samples)} 个已完成样本）")

    # 启动 Agent 链
    run_agent_chain(effective_id, ["__AUTO__"], up_to=up_to)

    # 管道健康检查（A~F 哪些成功/缺失）
    pipeline_status = validate_outputs(effective_id)

    # 载入生成后的题库（<conversation_id>_generated）
    generated_id = f"{effective_id}_generated"
    qb_generated = load_question_bank(generated_id)
    if qb_generated is None or not getattr(qb_generated, "questions", None):
        raise ValueError("题目生成流程已完成，但未找到生成题库文件。")

    question_count = len(qb_generated.questions)

    # 拿到 Agent F 的质量报告（如果有的话）
    quality_report = getattr(shared_state, "quality_report", None)

    return {
        "conversation_id": effective_id,
        "generated_conversation_id": generated_id,
        "question_count": question_count,
        "pipeline_status": pipeline_status,
        "quality_report": quality_report,
    }
