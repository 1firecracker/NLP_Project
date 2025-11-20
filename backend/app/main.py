from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import conversations, documents, graph, images, exercises

app = FastAPI(
    title="LightRAG Web Application",
    description="基于 LightRAG 的 Web 应用程序",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # 使用明确配置的端口列表
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # 暴露所有响应头，包括图片相关的
)

# 注册路由
app.include_router(conversations.router)
app.include_router(documents.router)
app.include_router(graph.router)
app.include_router(images.router)
app.include_router(exercises.router)

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "LightRAG Web Application API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
