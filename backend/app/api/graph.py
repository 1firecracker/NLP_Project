"""知识图谱查询 API"""
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.graph_service import GraphService
from app.services.memory_service import MemoryService

router = APIRouter(tags=["graph"])

# 请求/响应模型
class QueryRequest(BaseModel):
    query: str
    mode: Optional[str] = "naive"  # naive/local/global/mix

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


@router.get("/api/conversations/{conversation_id}/graph/relations",
            response_model=RelationResponse)
async def get_relation(
    conversation_id: str,
    source: str = Query(..., description="源实体ID"),
    target: str = Query(..., description="目标实体ID")
):
    """获取单个关系详情
    
    Args:
        conversation_id: 对话ID
        source: 源实体ID
        target: 目标实体ID
    """
    service = GraphService()
    
    relation = await service.get_relation_detail(conversation_id, source, target)
    
    if not relation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"关系 {source} -> {target} 不存在"
        )
    
    return RelationResponse(**relation)


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
        # 获取历史对话并计算 token（减少到3轮，并限制单条消息长度）
        memory_service = MemoryService()
        history = memory_service.get_recent_history(conversation_id, max_turns=3, max_tokens_per_message=500)
        token_stats = memory_service.calculate_input_tokens(request.query, history, request.mode)
        print(f"[Token统计] 模式={token_stats['mode']}, 查询={token_stats['query_tokens']}, "
              f"历史={token_stats['history_tokens']} (保留{token_stats['history_count']}条: "
              f"用户{token_stats['history_user_count']}条+助手{token_stats['history_assistant_count']}条), "
              f"总计={token_stats['total_input_tokens']}")
        
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
    
    当知识图谱为空或查询未匹配到相关内容时，会自动降级到 LLM 直接回答，并显示提示。
    
    Args:
        conversation_id: 对话ID
        request: 查询请求（包含 query 和 mode）
        
    Returns:
        StreamingResponse: NDJSON 格式的流式响应
        - 每行一个 JSON 对象：{"response": "chunk"} 或 {"warning": "message"}
        - 错误时：{"error": "error message"}
    """
    service = GraphService()
    memory_service = MemoryService()
    
    # 获取历史对话（减少到3轮，并限制单条消息长度）
    history = memory_service.get_recent_history(conversation_id, max_turns=3, max_tokens_per_message=500)
    
    # 计算并打印输入 token
    token_stats = memory_service.calculate_input_tokens(request.query, history, request.mode)
    print(f"[Token统计] 模式={token_stats['mode']}, 查询={token_stats['query_tokens']}, "
          f"历史={token_stats['history_tokens']} (保留{token_stats['history_count']}条: "
          f"用户{token_stats['history_user_count']}条+助手{token_stats['history_assistant_count']}条), "
          f"总计={token_stats['total_input_tokens']}")
    
    # 验证查询模式（排除 bypass 模式，因为 bypass 不检索）
    valid_modes = ["naive", "local", "global", "mix"]
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的查询模式: {request.mode}，支持的模式: {', '.join(valid_modes)}"
        )
    
    # 第一层：快速检查是否有文档（无需初始化 LightRAG）
    if not service.check_has_documents_fast(conversation_id):
        # 快速路径：直接使用 bypass 模式，无需初始化 LightRAG 和检查知识图谱
        async def fast_bypass_stream():
            try:
                # 发送警告提示
                warning_message = "[未上传文档 ,直接给出回答]"
                yield f"{json.dumps({'warning': warning_message})}\n"
                # 发送换行
                newline_text = '\n\n'
                yield f"{json.dumps({'response': newline_text})}\n"
                
                # 初始化 LightRAG（仅用于 bypass 模式，无需检查知识图谱）
                lightrag = await service.lightrag_service.get_lightrag_for_conversation(conversation_id)
                from lightrag import QueryParam
                
                # 使用 bypass 模式查询（包含历史对话）
                bypass_param = QueryParam(mode="bypass", stream=True)
                if history:
                    bypass_param.conversation_history = history
                bypass_result = await lightrag.aquery_llm(request.query, param=bypass_param)
                llm_response = bypass_result.get("llm_response", {})
                
                # 流式发送响应
                if llm_response.get("is_streaming"):
                    response_stream = llm_response.get("response_iterator")
                    if response_stream:
                        try:
                            async for chunk in response_stream:
                                if chunk:
                                    yield f"{json.dumps({'response': chunk})}\n"
                        except Exception as e:
                            yield f"{json.dumps({'error': str(e)})}\n"
                    else:
                        content = llm_response.get("content", "")
                        if content:
                            yield f"{json.dumps({'response': content})}\n"
                else:
                    content = llm_response.get("content", "")
                    if content:
                        yield f"{json.dumps({'response': content})}\n"
                    else:
                        yield f"{json.dumps({'error': 'No response generated'})}\n"
            except Exception as e:
                yield f"{json.dumps({'error': str(e)})}\n"
        
        return StreamingResponse(
            fast_bypass_stream(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    # 第二层：有文档，进入正常流程（包含知识图谱检查）
    async def stream_generator():
        try:
            # 步骤1：查询前检测知识图谱是否为空
            kg_empty_before, error_msg = await service.check_knowledge_graph_empty(conversation_id)
            
            if error_msg:
                # 检测出错，显示错误信息
                yield f"{json.dumps({'error': error_msg})}\n"
                return
            
            lightrag = await service.lightrag_service.get_lightrag_for_conversation(conversation_id)
            from lightrag import QueryParam
            
            # 如果查询前知识图谱为空，直接使用 bypass 模式，跳过查询
            if kg_empty_before:
                # 直接发送警告提示并使用 bypass 模式
                warning_message = "⚠️ 未检索到相关文档，将基于通用知识回答："
                yield f"{json.dumps({'warning': warning_message})}\n"
                # 发送换行（不能在 f-string 表达式中使用反斜杠）
                newline_text = '\n\n'
                yield f"{json.dumps({'response': newline_text})}\n"
                
                # 直接使用 bypass 模式查询（包含历史对话）
                bypass_param = QueryParam(mode="bypass", stream=True)
                if history:
                    bypass_param.conversation_history = history
                bypass_result = await lightrag.aquery_llm(request.query, param=bypass_param)
                llm_response = bypass_result.get("llm_response", {})
            else:
                # 步骤2：执行查询（知识图谱不为空，包含历史对话）
                param = QueryParam(mode=request.mode, stream=True)
                if history:
                    param.conversation_history = history
                result = await lightrag.aquery_llm(request.query, param=param)
                
                # 步骤3：查询后验证结果
                result_empty, no_content = await service.check_query_result_empty(result, kg_empty_before)
                
                # 判断是否需要降级到 bypass 模式
                need_fallback = False
                warning_message = None
                
                if result_empty:
                    if no_content:
                        # 有知识图谱但查询未匹配到相关内容
                        need_fallback = True
                        warning_message = "⚠️ 未检索到相关内容，将基于通用知识回答："
                    else:
                        # 其他情况（查询失败等）
                        need_fallback = True
                        warning_message = "⚠️ 未检索到相关文档，将基于通用知识回答："
                elif result.get("status") == "failure":
                    # 查询失败
                    need_fallback = True
                    warning_message = "⚠️ 未检索到相关文档，将基于通用知识回答："
                
                # 如果需要降级，使用 bypass 模式重新查询
                if need_fallback:
                    # 先发送警告提示
                    if warning_message:
                        yield f"{json.dumps({'warning': warning_message})}\n"
                        # 发送换行（不能在 f-string 表达式中使用反斜杠）
                        newline_text = '\n\n'
                        yield f"{json.dumps({'response': newline_text})}\n"
                    
                    # 使用 bypass 模式重新查询（包含历史对话）
                    bypass_param = QueryParam(mode="bypass", stream=True)
                    if history:
                        bypass_param.conversation_history = history
                    bypass_result = await lightrag.aquery_llm(request.query, param=bypass_param)
                    
                    llm_response = bypass_result.get("llm_response", {})
                else:
                    # 正常使用查询结果
                    llm_response = result.get("llm_response", {})
            
            # 步骤4：流式发送响应
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

