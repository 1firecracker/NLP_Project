"""知识图谱服务"""
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from app.services.lightrag_service import LightRAGService
from app.services.document_service import DocumentService
from app.services.memory_service import MemoryService


class GraphService:
    """知识图谱服务，封装 LightRAG 查询功能"""
    
    def __init__(self):
        self.lightrag_service = LightRAGService()
        self.document_service = DocumentService()
        from app.services.conversation_service import ConversationService
        self.conversation_service = ConversationService()
        self.memory_service = MemoryService()
    
    def _parse_file_path_to_doc_info(self, file_path: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        """解析 file_path 到文档信息
        
        Args:
            file_path: 文件路径（如 "uploads/conversations/{conversation_id}/documents/{file_id}.pptx"）
            conversation_id: 对话ID
            
        Returns:
            文档信息字典，包含 file_id 和 filename，如果无法解析返回 None
        """
        if not file_path or file_path == "unknown_source":
            return None
        
        try:
            # 从路径中提取 file_id
            # 路径格式：uploads/conversations/{conversation_id}/documents/{file_id}.{ext}
            path_obj = Path(file_path)
            if path_obj.suffix:  # 有扩展名
                file_id = path_obj.stem  # 文件名（不含扩展名）
            else:
                return None
            
            # 获取文档信息
            status = self.document_service._load_status(conversation_id)
            for doc_id, doc_data in status.get("documents", {}).items():
                if doc_id == file_id:
                    return {
                        "file_id": doc_id,
                        "filename": doc_data.get("filename", path_obj.name),
                        "file_type": path_obj.suffix.lower()
                    }
            
            return None
        except Exception:
            return None
    
    async def _get_source_chunks_info(self, lightrag, source_id: str) -> List[Dict[str, Any]]:
        """从 source_id 获取 chunk 信息，用于映射到文档
        
        Args:
            lightrag: LightRAG 实例
            source_id: source_id（可能是多个 chunk_id 用分隔符连接）
            
        Returns:
            chunk 信息列表
        """
        if not source_id:
            return []
        
        chunks_info = []
        try:
            # source_id 可能是多个 chunk_id 用 GRAPH_FIELD_SEP 分隔
            # 先尝试分割
            chunk_ids = source_id.split("|") if "|" in source_id else [source_id]
            
            for chunk_id in chunk_ids:
                if not chunk_id or not chunk_id.startswith("chunk-"):
                    continue
                
                # 从 text_chunks 获取 chunk 信息
                try:
                    chunk_data = await lightrag.text_chunks.get_by_id(chunk_id)
                    if chunk_data:
                        chunks_info.append({
                            "chunk_id": chunk_id,
                            "file_path": chunk_data.get("file_path", ""),
                            "full_doc_id": chunk_data.get("full_doc_id", ""),
                            "chunk_order_index": chunk_data.get("chunk_order_index", 0),
                        })
                except Exception:
                    continue
        except Exception:
            pass
        
        return chunks_info
    
    async def get_all_entities(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取对话的所有实体
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            实体列表
        """
        lightrag = await self.lightrag_service.get_lightrag_for_conversation(conversation_id)
        
        # 获取所有节点（实体）
        entities = await lightrag.chunk_entity_relation_graph.get_all_nodes()
        
        # entities 已经是 list[dict] 格式
        entity_list = []
        for entity_data in entities:
            # entity_data 是字典，id 字段就是节点ID（实体名称）
            entity_id = entity_data.get("id", "")
            source_id = entity_data.get("source_id", "")
            file_path = entity_data.get("file_path", "")
            
            # 解析来源信息
            source_documents = []
            if source_id:
                chunks_info = await self._get_source_chunks_info(lightrag, source_id)
                # 从 chunks 中提取唯一的文档信息
                seen_file_ids = set()
                for chunk_info in chunks_info:
                    chunk_file_path = chunk_info.get("file_path", "")
                    if chunk_file_path and chunk_file_path != "unknown_source":
                        doc_info = self._parse_file_path_to_doc_info(chunk_file_path, conversation_id)
                        if doc_info and doc_info["file_id"] not in seen_file_ids:
                            seen_file_ids.add(doc_info["file_id"])
                            source_documents.append(doc_info)
            elif file_path and file_path != "unknown_source":
                # 如果没有 source_id，尝试直接从 file_path 解析
                doc_info = self._parse_file_path_to_doc_info(file_path, conversation_id)
                if doc_info:
                    source_documents.append(doc_info)
            
            entity_list.append({
                "entity_id": entity_id,
                "name": entity_id,  # 节点ID就是实体名称
                "type": entity_data.get("entity_type", entity_data.get("type", "")),
                "description": entity_data.get("description", ""),
                "source_id": source_id,
                "file_path": file_path,
                "source_documents": source_documents,  # 来源文档列表
            })
        
        return entity_list
    
    async def get_all_relations(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取对话的所有关系
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            关系列表
        """
        lightrag = await self.lightrag_service.get_lightrag_for_conversation(conversation_id)
        
        # 获取所有边（关系）
        relations = await lightrag.chunk_entity_relation_graph.get_all_edges()
        
        # relations 已经是 list[dict] 格式
        relation_list = []
        for relation_data in relations:
            # source 和 target 已经在边数据中
            relation_list.append({
                "relation_id": f"{relation_data.get('source', '')}->{relation_data.get('target', '')}",
                "source": relation_data.get("source", ""),
                "target": relation_data.get("target", ""),
                "type": relation_data.get("relation_type", relation_data.get("type", "")),
                "description": relation_data.get("description", ""),
            })
        
        return relation_list
    
    async def get_entity_detail(self, conversation_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """获取实体详情
        
        Args:
            conversation_id: 对话ID
            entity_id: 实体ID
            
        Returns:
            实体详情，如果不存在返回 None
        """
        entities = await self.get_all_entities(conversation_id)
        
        for entity in entities:
            if entity["entity_id"] == entity_id:
                return entity
        
        return None
    
    async def get_relation_detail(self, conversation_id: str, source: str, target: str) -> Optional[Dict[str, Any]]:
        """获取关系详情
        
        Args:
            conversation_id: 对话ID
            source: 源实体ID
            target: 目标实体ID
            
        Returns:
            关系详情，如果不存在返回 None
        """
        relations = await self.get_all_relations(conversation_id)
        
        for relation in relations:
            if relation["source"] == source and relation["target"] == target:
                return relation
        
        return None
    
    def check_has_documents_fast(self, conversation_id: str) -> bool:
        """快速检查对话是否有文档（无需初始化 LightRAG）
        
        通过检查对话元数据中的 file_count 或文档状态文件来判断。
        这是一个轻量级的检查，用于在查询前快速判断是否需要初始化 LightRAG。
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            True 表示有文档，False 表示没有文档
        """
        try:
            # 方式1：检查对话元数据中的 file_count（最快）
            conversation = self.conversation_service.get_conversation(conversation_id)
            if conversation:
                file_count = conversation.get("file_count", 0)
                if file_count > 0:
                    return True
            
            # 方式2：检查文档状态文件（更准确，但稍慢）
            status = self.document_service._load_status(conversation_id)
            documents = status.get("documents", {})
            if documents:
                # 检查是否有已处理的文档
                for doc_id, doc_data in documents.items():
                    doc_status = doc_data.get("status", "")
                    # 如果文档状态是 completed 或 processing，认为有文档
                    if doc_status in ["completed", "processing"]:
                        return True
            
            # 都没有，返回 False
            return False
            
        except Exception:
            # 检查出错时，保守起见返回 True（假设有文档，进入正常流程）
            return True
    
    async def check_knowledge_graph_empty(self, conversation_id: str) -> tuple[bool, Optional[str]]:
        """检测知识图谱是否为空
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            (is_empty, error_message): 
            - is_empty: True 表示知识图谱为空（实体=0 且 关系=0 且 文档块=0）
            - error_message: 如果检测过程中出错，返回错误信息；否则为 None
        """
        try:
            lightrag = await self.lightrag_service.get_lightrag_for_conversation(conversation_id)
            
            # 检查实体数量
            entities = await lightrag.chunk_entity_relation_graph.get_all_nodes()
            entity_count = len(entities) if entities else 0
            
            # 检查关系数量
            relations = await lightrag.chunk_entity_relation_graph.get_all_edges()
            relation_count = len(relations) if relations else 0
            
            # 检查文档块数量（通过检查 chunks_vdb 或 text_chunks）
            # 注意：chunks_vdb 可能没有直接的 count 方法，需要尝试其他方式
            chunk_count = 0
            try:
                # 尝试通过查询一个空查询来获取总数（如果 API 支持）
                # 或者通过检查 text_chunks 的键数量
                # 这里使用一个简单的检查：尝试获取一些 chunks
                # 由于 LightRAG 的存储结构，我们可能需要通过其他方式检查
                # 暂时先检查实体和关系，如果都为空，认为可能没有文档块
                pass
            except Exception:
                # 如果无法检查文档块数量，仅基于实体和关系判断
                pass
            
            # 判定标准：实体=0 且 关系=0 才判定为空
            # 注意：文档块数量检查可能较复杂，暂时主要依赖实体和关系
            is_empty = (entity_count == 0 and relation_count == 0)
            
            return is_empty, None
            
        except Exception as e:
            # 检测过程中出错，返回错误信息
            return False, f"检测知识图谱状态时出错: {str(e)}"
    
    async def check_query_result_empty(self, query_result: Dict[str, Any], kg_empty_before: bool) -> tuple[bool, bool]:
        """检查查询结果是否为空
        
        Args:
            query_result: aquery_llm 返回的结果字典
            kg_empty_before: 查询前知识图谱是否为空
            
        Returns:
            (is_empty, is_no_content):
            - is_empty: True 表示查询结果为空（实体=0 且 关系=0 且 文档块=0）
            - is_no_content: True 表示查询未匹配到相关内容（查询前有知识图谱，但查询后无结果）
        """
        try:
            # 如果查询状态为失败，直接判定为空
            if query_result.get("status") == "failure":
                return True, False
            
            data = query_result.get("data", {})
            
            entities = data.get("entities", [])
            relationships = data.get("relationships", [])
            chunks = data.get("chunks", [])
            
            entity_count = len(entities) if entities else 0
            relation_count = len(relationships) if relationships else 0
            chunk_count = len(chunks) if chunks else 0
            
            # 全部为空：判定为查询结果为空
            is_empty = (entity_count == 0 and relation_count == 0 and chunk_count == 0)
            
            # 查询未匹配到相关内容：查询前有知识图谱，但查询后无结果
            is_no_content = (not kg_empty_before and is_empty)
            
            return is_empty, is_no_content
            
        except Exception:
            # 解析失败，假设不为空
            return False, False
    
    async def query(self, conversation_id: str, query: str, mode: str = "mix", use_history: bool = True) -> str:
        """在对话的知识图谱中查询
        
        Args:
            conversation_id: 对话ID
            query: 查询文本
            mode: 查询模式（naive/local/global/mix）
            use_history: 是否使用历史对话
            
        Returns:
            查询结果（文本）
        """
        # 获取历史对话（减少到3轮，并限制单条消息长度）
        history = []
        if use_history:
            history = self.memory_service.get_recent_history(conversation_id, max_turns=3, max_tokens_per_message=1000)
        
        result = await self.lightrag_service.query(conversation_id, query, mode=mode, conversation_history=history)
        
        # 如果结果是字符串，直接返回
        if isinstance(result, str):
            return result
        
        # 如果是其他类型，转换为字符串
        return str(result)

