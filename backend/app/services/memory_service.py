"""对话记忆服务 - 轻量级实现"""
from typing import List, Dict, Optional
from app.services.conversation_service import ConversationService


def estimate_tokens(text: str) -> int:
    """简单估算 token 数量（中文按字，英文按词）
    
    Args:
        text: 文本内容
        
    Returns:
        估算的 token 数量
    """
    if not text:
        return 0
    # 简单估算：中文字符数 + 英文单词数 * 1.3（考虑标点等）
    import re
    chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
    english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
    other_chars = len(text) - chinese_chars - sum(len(m) for m in re.findall(r'\b[a-zA-Z]+\b', text))
    # 估算：中文字符按1 token，英文单词按1.3 token，其他字符按0.5 token
    return int(chinese_chars + english_words * 1.3 + other_chars * 0.5)


class MemoryService:
    """对话记忆服务，提供历史对话获取和关键词匹配"""
    
    def __init__(self):
        self.conversation_service = ConversationService()
    
    def get_recent_history(self, conversation_id: str, max_turns: int = 5, max_tokens_per_message: int = 1000) -> List[Dict[str, str]]:
        """获取最近的对话历史
        
        Args:
            conversation_id: 对话ID
            max_turns: 最大轮次（每轮包含user和assistant两条消息）
            max_tokens_per_message: 每条消息的最大 token 数（超过会截断）
            
        Returns:
            格式化的历史消息列表，格式: [{"role": "user/assistant", "content": "..."}]
        """
        messages = self.conversation_service.get_messages(conversation_id)
        
        if not messages:
            return []
        
        # 只取最近的 max_turns 轮（每轮2条消息）
        recent_messages = messages[-(max_turns * 2):] if len(messages) > max_turns * 2 else messages
        
        # 转换为 LightRAG 需要的格式，并对长消息进行截断
        history = []
        for msg in recent_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role and content:
                # 如果消息太长，进行截断
                if max_tokens_per_message > 0:
                    tokens = estimate_tokens(content)
                    if tokens > max_tokens_per_message:
                        # 简单截断：保留前面的内容
                        # 更智能的方式是按句子截断，这里先用简单方式
                        char_limit = max_tokens_per_message * 2  # 粗略估算字符数
                        if len(content) > char_limit:
                            content = content[:char_limit] + "...[已截断]"
                
                history.append({
                    "role": role,
                    "content": content
                })
        
        return history
    
    def calculate_input_tokens(self, query: str, history: List[Dict[str, str]], mode: str) -> Dict[str, int]:
        """计算输入 token 数量
        
        Args:
            query: 当前查询
            history: 历史对话
            mode: 查询模式
            
        Returns:
            token 统计字典，包含详细信息
        """
        query_tokens = estimate_tokens(query)
        history_tokens = sum(estimate_tokens(msg.get("content", "")) for msg in history)
        total_input_tokens = query_tokens + history_tokens
        
        # 统计历史消息数量
        history_count = len(history)
        user_messages = sum(1 for msg in history if msg.get("role") == "user")
        assistant_messages = sum(1 for msg in history if msg.get("role") == "assistant")
        
        return {
            "query_tokens": query_tokens,
            "history_tokens": history_tokens,
            "total_input_tokens": total_input_tokens,
            "mode": mode,
            "history_count": history_count,
            "history_user_count": user_messages,
            "history_assistant_count": assistant_messages
        }
    
    def match_keywords(self, query: str, history: List[Dict[str, str]], keywords: Optional[List[str]] = None) -> bool:
        """简单的关键词匹配
        
        Args:
            query: 当前查询
            history: 历史对话
            keywords: 关键词列表（可选，如果为None则自动提取）
            
        Returns:
            是否匹配到相关历史
        """
        if not history:
            return False
        
        # 如果没有提供关键词，从查询中提取简单关键词（中文单字或英文单词）
        if keywords is None:
            # 简单提取：去除标点，保留中文字符和英文单词
            import re
            keywords = re.findall(r'[\u4e00-\u9fa5]|\b\w+\b', query.lower())
        
        # 检查历史对话中是否包含这些关键词
        history_text = " ".join([msg.get("content", "") for msg in history]).lower()
        
        for keyword in keywords:
            if keyword and keyword in history_text:
                return True
        
        return False

