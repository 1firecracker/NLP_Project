"""完整修复 exercise_service.py"""

filepath = r'c:\Users\19668\Desktop\workspace\NLP_Project\backend\app\services\exercise_service.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到 generate_questions 方法开始的行
start_idx = None
for i, line in enumerate(lines):
    if 'def generate_questions(self, conversation_id: str, up_to: str = "F") -> Dict:' in line:
        start_idx = i
        break

if start_idx is None:
    print("❌ 未找到 generate_questions 方法")
    exit(1)

# 找到方法体开始（文档字符串后）
doc_end = None
for i in range(start_idx + 1, min(start_idx + 20, len(lines))):
    if '"""' in lines[i] and i > start_idx + 1:
        doc_end = i
        break

if doc_end is None:
    print("❌ 未找到文档字符串结束")
    exit(1)

# 找到下一个方法开始的行（或文件结束）
next_method = None
for i in range(doc_end + 1, len(lines)):
    if lines[i].strip().startswith('def ') and not lines[i].strip().startswith('# '):
        next_method = i
        break

if next_method is None:
    next_method = len(lines)

# 新的方法实现
new_implementation = '''        # 只使用当前 conversation_id，不再自动查找其他会话
        effective_id = conversation_id
        samples = self.list_samples(conversation_id)

        # 检查当前会话是否有已完成的样本
        if not samples:
            raise ValueError(
                f"当前会话 [{conversation_id}] 未找到任何样本试卷。\\n"
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

'''

# 保留方法定义和文档字符串，替换实现
new_lines = lines[:doc_end + 1] + [new_implementation] + lines[next_method:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"✅ 已更新 generate_questions 方法 (行 {start_idx + 1} 到 {next_method})")
