"""知识图谱服务"""
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from app.services.lightrag_service import LightRAGService
from app.services.document_service import DocumentService


class GraphService:
    """知识图谱服务，封装 LightRAG 查询功能"""
    
    def __init__(self):
        self.lightrag_service = LightRAGService()
        self.document_service = DocumentService()
    
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
    
    async def query(self, conversation_id: str, query: str, mode: str = "mix") -> str:
        """在对话的知识图谱中查询
        
        Args:
            conversation_id: 对话ID
            query: 查询文本
            mode: 查询模式（naive/local/global/mix）
            
        Returns:
            查询结果（文本）
        """
        result = await self.lightrag_service.query(conversation_id, query, mode=mode)
        
        # 如果结果是字符串，直接返回
        if isinstance(result, str):
            return result
        
        # 如果是其他类型，转换为字符串
        return str(result)

