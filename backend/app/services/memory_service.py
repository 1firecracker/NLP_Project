"""对话记忆服务 - 轻量级实现"""
from typing import List, Dict, Optional
from app.services.conversation_service import ConversationService


class MemoryService:
    """对话记忆服务，提供历史对话获取和关键词匹配"""
    
    def __init__(self):
        self.conversation_service = ConversationService()
    
    def get_recent_history(self, conversation_id: str, max_turns: int = 5) -> List[Dict[str, str]]:
        """获取最近的对话历史
        
        Args:
            conversation_id: 对话ID
            max_turns: 最大轮次（每轮包含user和assistant两条消息）
            
        Returns:
            格式化的历史消息列表，格式: [{"role": "user/assistant", "content": "..."}]
        """
        messages = self.conversation_service.get_messages(conversation_id)
        
        if not messages:
            return []
        
        # 只取最近的 max_turns 轮（每轮2条消息）
        recent_messages = messages[-(max_turns * 2):] if len(messages) > max_turns * 2 else messages
        
        # 转换为 LightRAG 需要的格式
        history = []
        for msg in recent_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role and content:
                history.append({
                    "role": role,
                    "content": content
                })
        
        return history
    
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

