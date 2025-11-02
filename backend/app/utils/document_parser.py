"""统一文档解析接口"""
from typing import Dict, Any, List
from pathlib import Path
from app.utils.ppt_parser import PPTParser
from app.utils.pdf_parser import PDFParser


class DocumentParser:
    """文档解析器统一接口"""
    
    def __init__(self):
        self.ppt_parser = PPTParser()
        self.pdf_parser = PDFParser()
    
    def parse(self, file_path: str) -> Dict[str, Any]:
        """解析文档，返回结构化数据
        
        Args:
            file_path: 文档文件路径
            
        Returns:
            结构化文档数据
            
        Raises:
            ValueError: 不支持的文件类型
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        if suffix == '.pptx':
            return self.ppt_parser.parse(file_path)
        elif suffix == '.pdf':
            return self.pdf_parser.parse(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {suffix}，仅支持 .pptx 和 .pdf")
    
    def extract_text(self, file_path: str) -> str:
        """提取文档纯文本内容
        
        Args:
            file_path: 文档文件路径
            
        Returns:
            文档的纯文本内容
            
        Raises:
            ValueError: 不支持的文件类型
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        if suffix == '.pptx':
            return self.ppt_parser.extract_text(file_path)
        elif suffix == '.pdf':
            return self.pdf_parser.extract_text(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {suffix}，仅支持 .pptx 和 .pdf")
    
    def extract_text_positions(self, file_path: str, slide_or_page_number: int) -> Dict[str, Any]:
        """提取文档指定页面/幻灯片的文本位置信息
        
        Args:
            file_path: 文档文件路径
            slide_or_page_number: 幻灯片/页面编号（从1开始）
            
        Returns:
            包含文本位置列表和尺寸信息的字典
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        if suffix == '.pptx':
            result = self.ppt_parser.extract_text_positions(file_path, slide_or_page_number)
            # 统一字段名：slide_dimensions -> dimensions
            if result.get("slide_dimensions"):
                result["dimensions"] = result.pop("slide_dimensions")
            return result
        elif suffix == '.pdf':
            result = self.pdf_parser.extract_text_positions(file_path, slide_or_page_number)
            # 统一字段名：page_dimensions -> dimensions
            if result.get("page_dimensions"):
                result["dimensions"] = result.pop("page_dimensions")
            return result
        else:
            raise ValueError(f"不支持的文件类型: {suffix}，仅支持 .pptx 和 .pdf")
    
    @staticmethod
    def is_supported(file_path: str) -> bool:
        """检查文件类型是否支持
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否支持
        """
        suffix = Path(file_path).suffix.lower()
        return suffix in ['.pptx', '.pdf']

