from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用配置"""
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    # LightRAG 配置（后续使用）
    lightrag_working_dir: str = "./data/.lightrag"
    lightrag_kv_storage: str = "JsonKVStorage"
    lightrag_vector_storage: str = "NanoVectorDBStorage"
    lightrag_graph_storage: str = "NetworkXStorage"
    lightrag_doc_status_storage: str = "JsonDocStatusStorage"
    
    # LLM 配置
    llm_binding: str = "openai"
    llm_model: str = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
    llm_binding_api_key: str = ""  # 必需：从环境变量读取，请配置 LLM_BINDING_API_KEY
    llm_binding_host: str = "https://api.siliconflow.cn/v1"
    max_async: int = 16 
    timeout: int = 400  # 增加超时时间，避免复杂内容处理超时（从150增加到400）
    
    # Embedding 配置
    embedding_binding: str = "siliconcloud"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dim: int = 1024
    embedding_binding_host: str = "http://localhost:11434"
    
    # 文件上传配置
    upload_dir: str = str(BASE_DIR / "uploads")
    max_file_size: int = 52428800  # 50MB
    allowed_extensions: List[str] = ["pptx", "ppt", "pdf"]
    max_files_per_conversation: int = 20  # 每个对话最多文件数
    
    # 对话和元数据存储配置
    conversations_metadata_dir: str = str(BASE_DIR / "uploads/metadata")
    conversations_dir: str = str(BASE_DIR / "uploads/conversations")
    
    # 数据存储目录配置（用于批改记录、学习建议等）
    data_dir: str = str(BASE_DIR / "data")
    
    # 图片渲染配置
    image_cache_dir: str = str(BASE_DIR / "uploads/image_cache")
    image_resolution: int = 150  # DPI
    image_cache_expiry_hours: int = 24  # 缓存过期时间（小时）
    enable_image_cache: bool = True  # 是否启用图片缓存
    
    # 样本试题配置
    exercises_dir: str = str(BASE_DIR / "uploads/exercises")
    exercise_allowed_extensions: List[str] = ["pdf", "docx", "txt"]  # 样本试题支持的文件类型
    max_samples_per_conversation: int = 50  # 每个对话最多样本试题数

    # 外部 PaddleOCR（Gitee）配置
    enable_gitee_ocr: bool = True
    gitee_ocr_token: str = ""
    gitee_ocr_timeout: int = 30
    gitee_ocr_max_retry: int = 2
    gitee_ocr_poll_interval: int = 5
    gitee_ocr_max_wait: int = 60  # 秒，轮询总等待时长

    class Config:
        env_file = str(Path(__file__).resolve().parent.parent / ".env")
        case_sensitive = False
        extra = "ignore"

settings = Settings()
