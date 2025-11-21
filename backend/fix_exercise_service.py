"""
修复脚本：更新 exercise_service.py 中的 generate_questions 方法
"""
import re

# 读取原文件
with open(r'c:\Users\19668\Desktop\workspace\NLP_Project\backend\app\services\exercise_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加新方法 _clear_generated_cache (在 generate_questions 之前)
clear_cache_method = '''
    def _clear_generated_cache(self, conversation_id: str):
        """
        清除指定会话的生成题库缓存（磁盘文件和内存状态）
        """
        import os
        from app.agents.database.question_bank_storage import BASE_DATA_DIR
        
        # 清除内存缓存
        shared_state.reset()
        
        # 清除磁盘文件（_generated, _corrected, _graded）
        suffixes = ['_generated', '_corrected', '_graded']
        for suffix in suffixes:
            cache_id = f"{conversation_id}{suffix}"
            cache_dir = os.path.join(BASE_DATA_DIR, cache_dir)
            if os.path.exists(cache_dir):
                try:
                    shutil.rmtree(cache_dir)
                    print(f"[🗑️ 已清除缓存] {cache_dir}")
                except Exception as e:
                    print(f"[⚠️ 清除缓存失败] {cache_dir}: {e}")

'''

# 在 generate_questions 方法之前插入
if '_clear_generated_cache' not in content:
    content = content.replace(
        '    def generate_questions(self, conversation_id: str, up_to: str = "F") -> Dict:',
        clear_cache_method + '    def generate_questions(self, conversation_id: str, up_to: str = "F") -> Dict:'
    )

# 替换 generate_questions 方法的实现
old_impl = r'''        # 先尝试用"当前" conversation_id
        effective_id = conversation_id
        samples = self.list_samples(conversation_id)

        # 1\) 如果当前会话根本没有样本，或者没有任何 completed 的样本，就自动兜底
        if \(not samples\) or \(not any\(s\.get\("status"\) == "completed" for s in samples\)\):
            auto_conv = self\._find_any_completed_conversation\(\)
            if auto_conv is None:
                # 真·一个样本都没解析成功过
                raise ValueError\("找不到任何已上传且解析完成的样本试卷，请先在前端上传并等待解析完成。"\)
            effective_id = auto_conv
            samples = self\.list_samples\(effective_id\)

        # 打个日志（方便以后你调试）
        print\(f"\[AgentPipeline\] 使用会话 \{effective_id\} 作为出题输入（找到 \{len\(samples\)\} 个样本）"\)'''

new_impl = '''        # 只使用当前 conversation_id，不再自动查找其他会话
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
        
        print(f"[AgentPipeline] 使用会话 {effective_id} 生成新题目（找到 {len(completed_samples)} 个已完成样本）")'''

content = re.sub(old_impl, new_impl, content, flags=re.DOTALL)

# 写回文件
with open(r'c:\Users\19668\Desktop\workspace\NLP_Project\backend\app\services\exercise_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 已更新 exercise_service.py")
