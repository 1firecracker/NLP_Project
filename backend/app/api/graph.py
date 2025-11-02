"""知识图谱查询 API"""
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.graph_service import GraphService

router = APIRouter(tags=["graph"])

# 请求/响应模型
class QueryRequest(BaseModel):
    query: str
    mode: Optional[str] = "mix"  # naive/local/global/mix

class QueryResponse(BaseModel):
    conversation_id: str
    query: str
    mode: str
    result: str

class SourceDocument(BaseModel):
    """来源文档信息"""
    file_id: str
    filename: str
    file_type: str

class EntityResponse(BaseModel):
    entity_id: str
    name: str
    type: str
    description: str
    source_id: Optional[str] = None
    file_path: Optional[str] = None
    source_documents: List[SourceDocument] = []  # 来源文档列表

class RelationResponse(BaseModel):
    relation_id: str
    source: str
    target: str
    type: str
    description: str

class GraphResponse(BaseModel):
    entities: List[EntityResponse]
    relations: List[RelationResponse]
    total_entities: int
    total_relations: int


@router.get("/api/conversations/{conversation_id}/graph",
            response_model=GraphResponse)
async def get_graph(conversation_id: str):
    """获取对话的所有实体和关系
    
    Args:
        conversation_id: 对话ID
    """
    service = GraphService()
    
    try:
        entities = await service.get_all_entities(conversation_id)
        relations = await service.get_all_relations(conversation_id)
        
        # 转换实体数据，包括来源文档
        entity_responses = []
        for entity in entities:
            source_docs = [
                SourceDocument(**doc) for doc in entity.get("source_documents", [])
            ]
            entity_responses.append(EntityResponse(
                entity_id=entity["entity_id"],
                name=entity["name"],
                type=entity["type"],
                description=entity.get("description", ""),
                source_id=entity.get("source_id"),
                file_path=entity.get("file_path"),
                source_documents=source_docs
            ))
        
        return GraphResponse(
            entities=entity_responses,
            relations=[RelationResponse(**relation) for relation in relations],
            total_entities=len(entities),
            total_relations=len(relations)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取知识图谱失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/graph/entities/{entity_id}",
            response_model=EntityResponse)
async def get_entity(conversation_id: str, entity_id: str):
    """获取单个实体详情
    
    Args:
        conversation_id: 对话ID
        entity_id: 实体ID
    """
    service = GraphService()
    
    entity = await service.get_entity_detail(conversation_id, entity_id)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"实体 {entity_id} 不存在"
        )
    
    # 转换来源文档
    source_docs = [
        SourceDocument(**doc) for doc in entity.get("source_documents", [])
    ]
    
    return EntityResponse(
        entity_id=entity["entity_id"],
        name=entity["name"],
        type=entity["type"],
        description=entity.get("description", ""),
        source_id=entity.get("source_id"),
        file_path=entity.get("file_path"),
        source_documents=source_docs
    )


@router.post("/api/conversations/{conversation_id}/query",
            response_model=QueryResponse)
async def query_knowledge_graph(conversation_id: str, request: QueryRequest):
    """在对话的知识图谱中查询（非流式）
    
    支持不同的查询模式：
    - naive: 基础查询
    - local: 本地图谱查询
    - global: 全局查询
    - mix: 混合查询（默认）
    
    Args:
        conversation_id: 对话ID
        request: 查询请求（包含 query 和 mode）
    """
    service = GraphService()
    
    # 验证查询模式
    valid_modes = ["naive", "local", "global", "mix"]
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的查询模式: {request.mode}，支持的模式: {', '.join(valid_modes)}"
        )
    
    try:
        result = await service.query(conversation_id, request.query, request.mode)
        
        return QueryResponse(
            conversation_id=conversation_id,
            query=request.query,
            mode=request.mode,
            result=result
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}"
        )


@router.post("/api/conversations/{conversation_id}/query/stream")
async def query_knowledge_graph_stream(conversation_id: str, request: QueryRequest):
    """流式查询知识图谱（支持逐字显示）
    
    支持不同的查询模式：
    - naive: 基础查询
    - local: 本地图谱查询
    - global: 全局查询
    - mix: 混合查询（默认）
    
    Args:
        conversation_id: 对话ID
        request: 查询请求（包含 query 和 mode）
        
    Returns:
        StreamingResponse: NDJSON 格式的流式响应
        - 每行一个 JSON 对象：{"response": "chunk"}
        - 错误时：{"error": "error message"}
    """
    service = GraphService()
    
    # 验证查询模式
    valid_modes = ["naive", "local", "global", "mix"]
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的查询模式: {request.mode}，支持的模式: {', '.join(valid_modes)}"
        )
    
    async def stream_generator():
        try:
            # 调用流式查询
            lightrag = await service.lightrag_service.get_lightrag_for_conversation(conversation_id)
            from lightrag import QueryParam
            
            # 使用 aquery_llm 获取流式响应
            param = QueryParam(mode=request.mode, stream=True)
            result = await lightrag.aquery_llm(request.query, param=param)
            
            llm_response = result.get("llm_response", {})
            
            if llm_response.get("is_streaming"):
                # 流式模式：逐块发送响应
                response_stream = llm_response.get("response_iterator")
                if response_stream:
                    try:
                        async for chunk in response_stream:
                            if chunk:  # 只发送非空内容
                                yield f"{json.dumps({'response': chunk})}\n"
                    except Exception as e:
                        yield f"{json.dumps({'error': str(e)})}\n"
                else:
                    # 如果没有流式响应，发送完整内容
                    content = llm_response.get("content", "")
                    if content:
                        yield f"{json.dumps({'response': content})}\n"
            else:
                # 非流式模式：发送完整响应
                content = llm_response.get("content", "")
                if content:
                    yield f"{json.dumps({'response': content})}\n"
                else:
                    yield f"{json.dumps({'error': 'No response generated'})}\n"
                    
        except Exception as e:
            yield f"{json.dumps({'error': str(e)})}\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

