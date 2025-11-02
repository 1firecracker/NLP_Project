"""图片渲染 API"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, status, Response
from fastapi.responses import FileResponse
from typing import Optional

import app.config as config
from app.services.document_service import DocumentService
from app.utils.image_renderer import ImageRenderer

router = APIRouter(tags=["images"])

# 初始化图片渲染器
image_renderer = ImageRenderer(
    cache_dir=config.settings.image_cache_dir,
    resolution=config.settings.image_resolution,
    cache_expiry_hours=config.settings.image_cache_expiry_hours
)


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/slides/{slide_id}/image")
async def get_slide_image(
    conversation_id: str,
    file_id: str,
    slide_id: int,
    use_cache: bool = True
):
    """获取幻灯片/页面的渲染图片
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
        slide_id: 幻灯片/页面编号（从1开始）
        use_cache: 是否使用缓存（默认True）
    """
    service = DocumentService()
    
    # 获取文档信息
    document = service.get_document(conversation_id, file_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    file_extension = document["file_extension"]
    if file_extension not in ["pptx", "pdf"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此接口仅支持 PPTX 和 PDF 格式文件"
        )
    
    try:
        # 渲染图片
        image_path = image_renderer.get_image_path(
            file_path=document["file_path"],
            slide_number=slide_id,
            file_id=file_id,
            file_extension=file_extension,
            use_cache=use_cache,
            is_thumbnail=False
        )
        
        if not image_path or not image_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"图片渲染失败：无法生成幻灯片 {slide_id} 的图片"
            )
        
        # 返回文件响应
        response = FileResponse(
            path=str(image_path),
            media_type="image/png",
            filename=f"slide_{slide_id}.png"
        )
        # 显式添加CORS头（确保图片可以跨域加载）
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:5173"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取图片失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/slides/{slide_id}/thumbnail")
async def get_slide_thumbnail(
    conversation_id: str,
    file_id: str,
    slide_id: int,
    use_cache: bool = True
):
    """获取幻灯片/页面的缩略图
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
        slide_id: 幻灯片/页面编号（从1开始）
        use_cache: 是否使用缓存（默认True）
    """
    service = DocumentService()
    
    # 获取文档信息
    document = service.get_document(conversation_id, file_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    file_extension = document["file_extension"]
    if file_extension not in ["pptx", "pdf"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此接口仅支持 PPTX 和 PDF 格式文件"
        )
    
    try:
        # 渲染缩略图
        image_path = image_renderer.get_image_path(
            file_path=document["file_path"],
            slide_number=slide_id,
            file_id=file_id,
            file_extension=file_extension,
            use_cache=use_cache,
            is_thumbnail=True
        )
        
        if not image_path or not image_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"缩略图渲染失败：无法生成幻灯片 {slide_id} 的缩略图"
            )
        
        # 返回文件响应
        response = FileResponse(
            path=str(image_path),
            media_type="image/png",
            filename=f"slide_{slide_id}_thumb.png"
        )
        # 显式添加CORS头（确保图片可以跨域加载）
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:5173"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取缩略图失败: {str(e)}"
        )

