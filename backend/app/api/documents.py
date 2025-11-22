"""文档管理 API"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, status
from pydantic import BaseModel

from app.services.document_service import DocumentService
from app.utils.document_parser import DocumentParser

router = APIRouter(tags=["documents"])

# 响应模型
class DocumentResponse(BaseModel):
    file_id: str
    filename: str
    file_size: int
    status: str

class DocumentDetailResponse(BaseModel):
    file_id: str
    conversation_id: str
    filename: str
    file_size: int
    file_extension: str
    upload_time: str
    status: str
    lightrag_track_id: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentDetailResponse]
    total: int

class DocumentUploadResponse(BaseModel):
    conversation_id: str
    uploaded_files: List[DocumentResponse]
    total_files: int

class DocumentStatusResponse(BaseModel):
    file_id: str
    status: str
    lightrag_track_id: Optional[str] = None
    error: Optional[str] = None
    upload_time: str
    progress: Optional[dict] = None  # 进度信息


@router.post("/api/conversations/{conversation_id}/documents/upload", 
             response_model=DocumentUploadResponse,
             status_code=status.HTTP_201_CREATED)
async def upload_documents(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """上传文档到对话
    
    支持上传多个文件（最多20个）
    - 如果 conversation_id 为 "new"，则自动创建新对话
    - 如果 conversation_id 指定的对话不存在，则自动创建
    
    Args:
        conversation_id: 对话ID（使用 "new" 表示自动创建新对话）
        files: 文件列表
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要上传一个文件"
        )
    
    service = DocumentService()
    
    try:
        # 如果 conversation_id 是 "new"，转换为 None
        conv_id = None if conversation_id == "new" else conversation_id
        
        # 上传文档
        result = await service.upload_documents(conv_id, files)
        
        # 为每个上传的文件启动后台处理任务
        for uploaded_file in result["uploaded_files"]:
            background_tasks.add_task(
                service.process_document,
                result["conversation_id"],
                uploaded_file["file_id"]
            )
        
        return DocumentUploadResponse(**result)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传文档失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/documents",
            response_model=DocumentListResponse)
async def list_documents(conversation_id: str):
    """获取对话的所有文档列表
    
    Args:
        conversation_id: 对话ID
    """
    service = DocumentService()
    
    try:
        documents = service.list_documents(conversation_id)
        
        return DocumentListResponse(
            documents=[DocumentDetailResponse(**doc) for doc in documents],
            total=len(documents)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档列表失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/documents/{file_id}",
            response_model=DocumentDetailResponse)
async def get_document(conversation_id: str, file_id: str):
    """获取单个文档详情
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    
    document = service.get_document(conversation_id, file_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    return DocumentDetailResponse(**document)


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/status",
            response_model=DocumentStatusResponse)
async def get_document_status(conversation_id: str, file_id: str):
    """查询文档处理状态
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    
    status = await service.get_document_status(conversation_id, file_id)
    
    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    return DocumentStatusResponse(**status)


@router.delete("/api/conversations/{conversation_id}/documents/{file_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(conversation_id: str, file_id: str):
    """删除文档
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    
    document = service.get_document(conversation_id, file_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    success = await service.delete_document(conversation_id, file_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除文档失败"
        )
    
    return None


# 幻灯片相关 API
class SlideResponse(BaseModel):
    slide_number: int
    title: str
    text_content: str
    images: List[dict] = []
    structure: dict = {}
    text_positions: List[dict] = []  # 文本位置信息（用于Canvas叠加）
    slide_dimensions: Optional[dict] = None  # 幻灯片/页面尺寸信息（用于位置校正）

class SlideListResponse(BaseModel):
    filename: str
    total_slides: int
    slides: List[SlideResponse]


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/slides",
            response_model=SlideListResponse)
async def get_document_slides(conversation_id: str, file_id: str):
    """获取文档的所有幻灯片/页面列表
    
    支持 PPTX 和 PDF 格式
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    parser = DocumentParser()
    
    # 获取文档信息
    document = service.get_document(conversation_id, file_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    """文档管理 API"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, status
from pydantic import BaseModel

from app.services.document_service import DocumentService
from app.utils.document_parser import DocumentParser

router = APIRouter(tags=["documents"])

# 响应模型
class DocumentResponse(BaseModel):
    file_id: str
    filename: str
    file_size: int
    status: str

class DocumentDetailResponse(BaseModel):
    file_id: str
    conversation_id: str
    filename: str
    file_size: int
    file_extension: str
    upload_time: str
    status: str
    lightrag_track_id: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentDetailResponse]
    total: int

class DocumentUploadResponse(BaseModel):
    conversation_id: str
    uploaded_files: List[DocumentResponse]
    total_files: int

class DocumentStatusResponse(BaseModel):
    file_id: str
    status: str
    lightrag_track_id: Optional[str] = None
    error: Optional[str] = None
    upload_time: str
    progress: Optional[dict] = None  # 进度信息


@router.post("/api/conversations/{conversation_id}/documents/upload", 
             response_model=DocumentUploadResponse,
             status_code=status.HTTP_201_CREATED)
async def upload_documents(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """上传文档到对话
    
    支持上传多个文件（最多20个）
    - 如果 conversation_id 为 "new"，则自动创建新对话
    - 如果 conversation_id 指定的对话不存在，则自动创建
    
    Args:
        conversation_id: 对话ID（使用 "new" 表示自动创建新对话）
        files: 文件列表
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要上传一个文件"
        )
    
    service = DocumentService()
    
    try:
        # 如果 conversation_id 是 "new"，转换为 None
        conv_id = None if conversation_id == "new" else conversation_id
        
        # 上传文档
        result = await service.upload_documents(conv_id, files)
        
        # 为每个上传的文件启动后台处理任务
        for uploaded_file in result["uploaded_files"]:
            background_tasks.add_task(
                service.process_document,
                result["conversation_id"],
                uploaded_file["file_id"]
            )
        
        return DocumentUploadResponse(**result)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传文档失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/documents",
            response_model=DocumentListResponse)
async def list_documents(conversation_id: str):
    """获取对话的所有文档列表
    
    Args:
        conversation_id: 对话ID
    """
    service = DocumentService()
    
    try:
        documents = service.list_documents(conversation_id)
        
        return DocumentListResponse(
            documents=[DocumentDetailResponse(**doc) for doc in documents],
            total=len(documents)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档列表失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/documents/{file_id}",
            response_model=DocumentDetailResponse)
async def get_document(conversation_id: str, file_id: str):
    """获取单个文档详情
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    
    document = service.get_document(conversation_id, file_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    return DocumentDetailResponse(**document)


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/status",
            response_model=DocumentStatusResponse)
async def get_document_status(conversation_id: str, file_id: str):
    """查询文档处理状态
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    
    status = await service.get_document_status(conversation_id, file_id)
    
    if not status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    return DocumentStatusResponse(**status)


@router.delete("/api/conversations/{conversation_id}/documents/{file_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(conversation_id: str, file_id: str):
    """删除文档
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    
    document = service.get_document(conversation_id, file_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    success = await service.delete_document(conversation_id, file_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除文档失败"
        )
    
    return None


# 幻灯片相关 API
class SlideResponse(BaseModel):
    slide_number: int
    title: str
    text_content: str
    images: List[dict] = []
    structure: dict = {}
    text_positions: List[dict] = []  # 文本位置信息（用于Canvas叠加）
    slide_dimensions: Optional[dict] = None  # 幻灯片/页面尺寸信息（用于位置校正）

class SlideListResponse(BaseModel):
    filename: str
    total_slides: int
    slides: List[SlideResponse]


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/slides",
            response_model=SlideListResponse)
async def get_document_slides(conversation_id: str, file_id: str):
    """获取文档的所有幻灯片/页面列表
    
    支持 PPTX 和 PDF 格式
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
    """
    service = DocumentService()
    parser = DocumentParser()
    
    # 获取文档信息
    document = service.get_document(conversation_id, file_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    # 检查文件类型
    file_ext = document["file_extension"]
    if file_ext not in ["pptx", "pdf"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此接口仅支持 PPTX 和 PDF 格式文件"
        )
    
    try:
        # 解析文档
        parsed_data = parser.parse(document["file_path"])
        
        # 如果是PDF，需要将pages转换为slides格式
        if file_ext == "pdf":
            # PDF返回的是 pages，需要转换为 slides 格式
            slides_data = []
            for page in parsed_data.get("pages", []):
                # 跳过文本位置提取
                text_positions = []
                page_dimensions = None
                
                slide_data = {
                    "slide_number": page["page_number"],
                    "title": f"第 {page['page_number']} 页",  # PDF没有标题，使用页码
                    "text_content": page["text_content"],
                    "images": page.get("images", []),
                    "structure": page.get("structure", {}),
                    "text_positions": text_positions,  # 添加文本位置信息
                    "slide_dimensions": page_dimensions  # 添加尺寸信息
                }
                slides_data.append(slide_data)
            
            return SlideListResponse(
                filename=parsed_data["filename"],
                total_slides=parsed_data["total_pages"],
                slides=slides_data
            )
        else:
            # PPTX: 为每个幻灯片提取文本位置信息
            slides_data = []
            for slide in parsed_data.get("slides", []):
                # 跳过文本位置提取
                slide["text_positions"] = []
                slide["slide_dimensions"] = None
            
            return SlideListResponse(
                filename=parsed_data["filename"],
                total_slides=parsed_data["total_slides"],
                slides=parsed_data["slides"]
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析文档失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/slides/{slide_id}",
            response_model=SlideResponse)
async def get_document_slide(conversation_id: str, file_id: str, slide_id: int):
    """获取单个幻灯片/页面内容和元数据
    
    支持 PPTX 和 PDF 格式
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
        slide_id: 幻灯片/页面编号（从1开始）
    """
    service = DocumentService()
    parser = DocumentParser()
    
    # 获取文档信息
    document = service.get_document(conversation_id, file_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    # 检查文件类型
    file_ext = document["file_extension"]
    if file_ext not in ["pptx", "pdf"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此接口仅支持 PPTX 和 PDF 格式文件"
        )
    
    try:
        # 解析文档
        parsed_data = parser.parse(document["file_path"])
        
        # 跳过文本位置提取
        text_positions = []
        slide_dimensions = None
        
        if file_ext == "pdf":
            # PDF: 从 pages 中查找
            pages = parsed_data.get("pages", [])
            if slide_id < 1 or slide_id > len(pages):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"页面 {slide_id} 不存在（共 {len(pages)} 页）"
                )
            
            page = pages[slide_id - 1]
            # 转换为 slides 格式
            slide_data = {
                "slide_number": page["page_number"],
                "title": f"第 {page['page_number']} 页",
                "text_content": page["text_content"],
                "images": page.get("images", []),
                "structure": page.get("structure", {}),
                "text_positions": text_positions,
                "slide_dimensions": slide_dimensions  # 添加尺寸信息
            }
            return SlideResponse(**slide_data)
        else:
            # PPTX: 从 slides 中查找
            slides = parsed_data.get("slides", [])
            if slide_id < 1 or slide_id > len(slides):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"幻灯片 {slide_id} 不存在（共 {len(slides)} 张）"
                )
            
            slide = slides[slide_id - 1]
            slide["text_positions"] = text_positions
            slide["slide_dimensions"] = slide_dimensions  # 添加尺寸信息
            return SlideResponse(**slide)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析文档失败: {str(e)}"
        )


    # 检查文件类型
    file_ext = document["file_extension"]
    if file_ext not in ["pptx", "pdf"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此接口仅支持 PPTX 和 PDF 格式文件"
        )
    
    try:
        # 解析文档
        parsed_data = parser.parse(document["file_path"])
        
        # 如果是PDF，需要将pages转换为slides格式
        if file_ext == "pdf":
            # PDF返回的是 pages，需要转换为 slides 格式
            slides_data = []
            for page in parsed_data.get("pages", []):
                try:
                    # 提取文本位置信息
                    text_positions_result = parser.extract_text_positions(document["file_path"], page["page_number"])
                    text_positions = text_positions_result.get("text_items", [])
                    page_dimensions = text_positions_result.get("dimensions")  # DocumentParser已统一为dimensions
                    
                    # 调试日志
                    if len(text_positions) == 0:
                        print(f"Warning: PDF page {page['page_number']} has no text positions extracted")
                    else:
                        print(f"Extracted {len(text_positions)} text positions for PDF page {page['page_number']}")
                        if page_dimensions:
                            print(f"Page dimensions: {page_dimensions['width_inches']}\" × {page_dimensions['height_inches']}\"")
                except Exception as e:
                    print(f"Error extracting text positions for PDF page {page['page_number']}: {e}")
                    text_positions = []  # 设置空数组作为默认值
                    page_dimensions = None
                
                slide_data = {
                    "slide_number": page["page_number"],
                    "title": f"第 {page['page_number']} 页",  # PDF没有标题，使用页码
                    "text_content": page["text_content"],
                    "images": page.get("images", []),
                    "structure": page.get("structure", {}),
                    "text_positions": text_positions,  # 添加文本位置信息
                    "slide_dimensions": page_dimensions  # 添加尺寸信息
                }
                slides_data.append(slide_data)
            
            return SlideListResponse(
                filename=parsed_data["filename"],
                total_slides=parsed_data["total_pages"],
                slides=slides_data
            )
        else:
            # PPTX: 为每个幻灯片提取文本位置信息
            slides_data = []
            for slide in parsed_data.get("slides", []):
                slide_number = slide.get("slide_number", 0)
                try:
                    # 提取文本位置信息
                    text_positions_result = parser.extract_text_positions(document["file_path"], slide_number)
                    text_positions = text_positions_result.get("text_items", [])
                    slide_dimensions = text_positions_result.get("dimensions")  # DocumentParser已统一为dimensions
                    
                    # 添加到slide数据中
                    slide["text_positions"] = text_positions
                    slide["slide_dimensions"] = slide_dimensions  # 添加尺寸信息
                    
                    # 调试日志
                    if len(text_positions) == 0:
                        print(f"Warning: Slide {slide_number} has no text positions extracted")
                    else:
                        print(f"Extracted {len(text_positions)} text positions for slide {slide_number}")
                        if slide_dimensions:
                            print(f"Slide dimensions: {slide_dimensions['width_inches']}\" × {slide_dimensions['height_inches']}\"")
                except Exception as e:
                    print(f"Error extracting text positions for slide {slide_number}: {e}")
                    slide["text_positions"] = []  # 设置空数组作为默认值
                    slide["slide_dimensions"] = None
            
            return SlideListResponse(
                filename=parsed_data["filename"],
                total_slides=parsed_data["total_slides"],
                slides=parsed_data["slides"]
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析文档失败: {str(e)}"
        )


@router.get("/api/conversations/{conversation_id}/documents/{file_id}/slides/{slide_id}",
            response_model=SlideResponse)
async def get_document_slide(conversation_id: str, file_id: str, slide_id: int):
    """获取单个幻灯片/页面内容和元数据
    
    支持 PPTX 和 PDF 格式
    
    Args:
        conversation_id: 对话ID
        file_id: 文件ID
        slide_id: 幻灯片/页面编号（从1开始）
    """
    service = DocumentService()
    parser = DocumentParser()
    
    # 获取文档信息
    document = service.get_document(conversation_id, file_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {file_id} 不存在"
        )
    
    # 检查文件类型
    file_ext = document["file_extension"]
    if file_ext not in ["pptx", "pdf"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此接口仅支持 PPTX 和 PDF 格式文件"
        )
    
    try:
        # 解析文档
        parsed_data = parser.parse(document["file_path"])
        
        # 提取文本位置信息（用于Canvas叠加）
        try:
            text_positions_result = parser.extract_text_positions(document["file_path"], slide_id)
            text_positions = text_positions_result.get("text_items", [])
            slide_dimensions = text_positions_result.get("dimensions")  # DocumentParser已统一为dimensions
        except Exception as e:
            print(f"Error extracting text positions for {file_ext} {slide_id}: {e}")
            text_positions = []
            slide_dimensions = None
        
        if file_ext == "pdf":
            # PDF: 从 pages 中查找
            pages = parsed_data.get("pages", [])
            if slide_id < 1 or slide_id > len(pages):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"页面 {slide_id} 不存在（共 {len(pages)} 页）"
                )
            
            page = pages[slide_id - 1]
            # 转换为 slides 格式
            slide_data = {
                "slide_number": page["page_number"],
                "title": f"第 {page['page_number']} 页",
                "text_content": page["text_content"],
                "images": page.get("images", []),
                "structure": page.get("structure", {}),
                "text_positions": text_positions,
                "slide_dimensions": slide_dimensions  # 添加尺寸信息
            }
            return SlideResponse(**slide_data)
        else:
            # PPTX: 从 slides 中查找
            slides = parsed_data.get("slides", [])
            if slide_id < 1 or slide_id > len(slides):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"幻灯片 {slide_id} 不存在（共 {len(slides)} 张）"
                )
            
            slide = slides[slide_id - 1]
            slide["text_positions"] = text_positions
            slide["slide_dimensions"] = slide_dimensions  # 添加尺寸信息
            return SlideResponse(**slide)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析文档失败: {str(e)}"
        )

