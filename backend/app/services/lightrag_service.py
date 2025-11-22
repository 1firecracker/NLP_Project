import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import app.config as config

# 添加 LightRAG 路径到 sys.path（必须在导入之前）
LIGHTRAG_BASE_PATH = Path(__file__).parent.parent.parent.parent / "LightRAG"
if str(LIGHTRAG_BASE_PATH) not in sys.path:
    sys.path.insert(0, str(LIGHTRAG_BASE_PATH))

# 现在可以导入 LightRAG
from lightrag import LightRAG
from lightrag.kg.shared_storage import initialize_pipeline_status, get_namespace_data
from lightrag.utils import EmbeddingFunc


class LightRAGService:
    """LightRAG 服务封装，支持对话隔离"""
    
    _instance: Optional['LightRAGService'] = None
    _lightrag_instances: Dict[str, LightRAG] = {}  # conversation_id -> LightRAG 实例
    _initialized_instances: Dict[str, bool] = {}  # conversation_id -> 是否已初始化
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lightrag_instances = {}
            cls._instance._initialized_instances = {}
        return cls._instance
    
    async def _init_lightrag_for_conversation(self, conversation_id: str) -> LightRAG:
        """为指定对话初始化 LightRAG 实例
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            LightRAG 实例
        """
        # 如果已经初始化，直接返回
        if conversation_id in self._lightrag_instances and self._initialized_instances.get(conversation_id, False):
            return self._lightrag_instances[conversation_id]
        
        # 为每个对话创建独立的工作目录
        base_working_dir = Path(config.settings.lightrag_working_dir)
        working_dir = base_working_dir.parent / conversation_id
        working_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置 LLM 函数
        llm_func = self._get_llm_func()
        
        # 配置 Embedding 函数
        embedding_func = self._get_embedding_func()
        
        # 创建 LightRAG 实例
        lightrag = LightRAG(
            working_dir=str(working_dir),
            llm_model_func=llm_func,
            embedding_func=embedding_func,
            kv_storage=config.settings.lightrag_kv_storage,
            vector_storage=config.settings.lightrag_vector_storage,
            graph_storage=config.settings.lightrag_graph_storage,
            doc_status_storage=config.settings.lightrag_doc_status_storage,
            chunk_token_size=600,  # 减小块大小，避免超时（从 1200 降到 600）
            chunk_overlap_token_size=50,  # 减小重叠（从 100 降到 50）
            workspace=conversation_id,  # 使用 conversation_id 作为 workspace
            default_llm_timeout=config.settings.timeout,  # 使用配置的超时时间（400秒）
        )
        
        # 初始化存储
        await lightrag.initialize_storages()
        await initialize_pipeline_status()
        
        # 缓存实例
        self._lightrag_instances[conversation_id] = lightrag
        self._initialized_instances[conversation_id] = True
        
        return lightrag
    
    def _get_llm_func(self):
        """获取 LLM 函数
        
        支持:
        - openai: OpenAI API 或兼容 OpenAI API 的服务（如硅基流动）
        - ollama: Ollama 本地模型
        """
        if config.settings.llm_binding == "openai":
            from lightrag.llm.openai import openai_complete_if_cache
            
            api_key = config.settings.llm_binding_api_key
            if not api_key:
                raise ValueError("LLM_BINDING_API_KEY 未配置")
            
            # 支持 OpenAI 兼容 API（如硅基流动）
            # 使用 openai_complete_if_cache 函数，支持自定义模型名
            def llm_func(prompt, **kwargs):
                # 移除可能的冲突参数
                kwargs.pop('api_base', None)
                # 使用配置的模型名，传递 base_url 和 api_key
                return openai_complete_if_cache(
                    model=config.settings.llm_model,
                    prompt=prompt,
                    api_key=api_key,
                    base_url=config.settings.llm_binding_host,
                    **kwargs
                )
            return llm_func
        elif config.settings.llm_binding == "ollama":
            from lightrag.llm.ollama import ollama_model_complete
            
            return lambda prompt, **kwargs: ollama_model_complete(
                prompt,
                model=config.settings.llm_model,
                host=config.settings.embedding_binding_host,
                timeout=config.settings.timeout,
                **kwargs
            )
        else:
            raise ValueError(f"不支持的 LLM binding: {config.settings.llm_binding}")
    
    def _get_embedding_func(self) -> EmbeddingFunc:
        """获取 Embedding 函数
        
        支持:
        - ollama: Ollama 本地模型
        - openai: OpenAI API 或兼容 OpenAI API 的服务
        - siliconcloud: 硅基流动 Embedding API
        """
        if config.settings.embedding_binding == "ollama":
            from lightrag.llm.ollama import ollama_embed
            
            return EmbeddingFunc(
                embedding_dim=config.settings.embedding_dim,
                max_token_size=8192,
                func=lambda texts: ollama_embed(
                    texts,
                    embed_model=config.settings.embedding_model,
                    host=config.settings.embedding_binding_host,
                )
            )
        elif config.settings.embedding_binding == "openai":
            from lightrag.llm.openai import openai_embed
            
            api_key = config.settings.llm_binding_api_key
            if not api_key:
                raise ValueError("LLM_BINDING_API_KEY 未配置（Embedding 需要）")
            
            # 支持 OpenAI 兼容 API（如硅基流动）
            from lightrag.llm.openai import openai_embed
            
            return EmbeddingFunc(
                embedding_dim=config.settings.embedding_dim,
                max_token_size=8192,
                func=lambda texts: openai_embed(
                    texts,
                    api_key=api_key,
                    base_url=config.settings.llm_binding_host,
                )
            )
        elif config.settings.embedding_binding == "siliconcloud":
            from lightrag.llm.siliconcloud import siliconcloud_embedding
            
            api_key = config.settings.llm_binding_api_key
            if not api_key:
                raise ValueError("LLM_BINDING_API_KEY 未配置（硅基流动需要）")
            
            # 硅基流动 Embedding API 地址
            embedding_base_url = config.settings.llm_binding_host.replace("/v1", "/v1/embeddings")
            if not embedding_base_url.endswith("/v1/embeddings"):
                embedding_base_url = "https://api.siliconflow.cn/v1/embeddings"
            
            return EmbeddingFunc(
                embedding_dim=config.settings.embedding_dim,
                max_token_size=8192,
                func=lambda texts: siliconcloud_embedding(
                    texts,
                    model=config.settings.embedding_model,
                    api_key=api_key,
                    base_url=embedding_base_url,
                )
            )
        else:
            raise ValueError(f"不支持的 Embedding binding: {config.settings.embedding_binding}")
    
    async def get_lightrag_for_conversation(self, conversation_id: str) -> LightRAG:
        """获取指定对话的 LightRAG 实例（延迟初始化）
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            LightRAG 实例
        """
        return await self._init_lightrag_for_conversation(conversation_id)
    
    async def insert_document(self, conversation_id: str, text: str, doc_id: Optional[str] = None) -> str:
        """异步插入文档到指定对话
        
        Args:
            conversation_id: 对话ID
            text: 文档文本内容
            doc_id: 文档ID（可选）
            
        Returns:
            track_id: LightRAG 处理跟踪ID
        """
        lightrag = await self.get_lightrag_for_conversation(conversation_id)
        # ainsert 使用 input 参数，doc_id 使用 ids 参数
        if doc_id:
            track_id = await lightrag.ainsert(input=text, ids=doc_id)
        else:
            track_id = await lightrag.ainsert(input=text)
        return track_id
    
    async def insert_file(self, conversation_id: str, file_path: str, doc_id: Optional[str] = None) -> str:
        """异步插入文件到指定对话
        
        Args:
            conversation_id: 对话ID
            file_path: 文件路径
            doc_id: 文档ID（可选）
            
        Returns:
            track_id: LightRAG 处理跟踪ID
        """
        lightrag = await self.get_lightrag_for_conversation(conversation_id)
        if doc_id:
            track_id = await lightrag.ainsert(file_paths=file_path, ids=doc_id)
        else:
            track_id = await lightrag.ainsert(file_paths=file_path)
        return track_id
    
    async def get_processing_progress(self, doc_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取处理进度信息
        
        Args:
            doc_id: 文档ID（可选），如果提供则只返回该文档的进度
            
        Returns:
            进度信息字典，包含 stage, current, total, percentage 等
        """
        try:
            pipeline_status = await get_namespace_data("pipeline_status", first_init=False)
            if not pipeline_status:
                return None
            
            progress = pipeline_status.get("progress")
            if not progress:
                return None
            
            # 如果指定了 doc_id，只返回匹配的进度
            if doc_id and progress.get("doc_id") != doc_id:
                return None
            
            return progress
        except Exception as e:
            # 如果 pipeline_status 未初始化或出错，返回 None
            return None
    
    async def query(self, conversation_id: str, query: str, mode: str = "mix", conversation_history: Optional[List[Dict[str, str]]] = None) -> Any:
        """在指定对话的知识图谱中查询
        
        Args:
            conversation_id: 对话ID
            query: 查询文本
            mode: 查询模式（naive/local/global/mix）
            conversation_history: 对话历史，格式: [{"role": "user/assistant", "content": "..."}]
            
        Returns:
            查询结果
        """
        lightrag = await self.get_lightrag_for_conversation(conversation_id)
        from lightrag import QueryParam
        param = QueryParam(mode=mode)
        if conversation_history:
            param.conversation_history = conversation_history
        result = await lightrag.aquery(query, param=param)
        return result
