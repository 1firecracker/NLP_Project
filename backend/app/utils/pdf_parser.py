"""PDF 文档解析器"""
import logging
# 关闭 pdfminer 的警告信息
logging.getLogger('pdfminer.pdfinterp').setLevel(logging.ERROR)
logging.getLogger('pdfminer').setLevel(logging.ERROR)

import pdfplumber
from typing import List, Dict, Any
from pathlib import Path


class PDFParser:
    """PDF 文档解析器"""
    
    def parse(self, file_path: str) -> Dict[str, Any]:
        """解析 PDF 文件，返回结构化数据
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            包含页面信息的字典
        """
        pages_data = []
        
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, 1):
                page_data = {
                    "page_number": page_num,
                    "text_content": self._extract_text(page),
                    "tables": self._extract_tables(page, page_num),
                    "images": self._extract_images(page, page_num),
                    "structure": self._extract_structure(page),
                }
                pages_data.append(page_data)
            
            # 尝试提取目录/大纲
            outline = self._extract_outline(pdf)
        
        return {
            "filename": Path(file_path).name,
            "total_pages": total_pages,
            "outline": outline,
            "pages": pages_data
        }
    
    def extract_text(self, file_path: str) -> str:
        """提取 PDF 的纯文本内容
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            所有页面文本内容（用换行符分隔）
        """
        texts = []
        
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    texts.append(text.strip())
        
        return "\n\n".join(texts)
    
    def _extract_text(self, page) -> str:
        """提取页面文本"""
        text = page.extract_text()
        return text.strip() if text else ""
    
    def _extract_tables(self, page, page_number: int) -> List[Dict[str, Any]]:
        """提取页面中的表格
        
        Args:
            page: PDF 页面对象
            page_number: 页面编号
            
        Returns:
            表格数据列表
        """
        tables = []
        extracted_tables = page.extract_tables()
        
        for idx, table in enumerate(extracted_tables):
            if table:
                table_data = {
                    "table_id": f"page_{page_number}_table_{idx}",
                    "rows": len(table),
                    "cols": len(table[0]) if table else 0,
                    "data": table
                }
                tables.append(table_data)
        
        return tables
    
    def _extract_images(self, page, page_number: int) -> List[Dict[str, Any]]:
        """提取页面中的图片元信息
        
        Args:
            page: PDF 页面对象
            page_number: 页面编号
            
        Returns:
            图片信息列表
        """
        images = []
        
        # pdfplumber 可以提取图片信息
        if hasattr(page, 'images') and page.images:
            for idx, img in enumerate(page.images):
                image_info = {
                    "image_id": f"page_{page_number}_img_{idx}",
                    "position": {
                        "x0": img.get("x0", 0),
                        "y0": img.get("y0", 0),
                        "x1": img.get("x1", 0),
                        "y1": img.get("y1", 0),
                        "width": img.get("width", 0),
                        "height": img.get("height", 0),
                    },
                    "name": img.get("name", f"Image {idx + 1}")
                }
                images.append(image_info)
        
        return images
    
    def _extract_structure(self, page) -> Dict[str, Any]:
        """提取页面结构信息"""
        return {
            "width": float(page.width),
            "height": float(page.height),
            "rotation": page.rotation if hasattr(page, "rotation") else 0
        }
    
    def extract_text_positions(self, file_path: str, page_number: int) -> Dict[str, Any]:
        """提取指定PDF页面的文本及其位置信息（用于Canvas精确叠加）
        
        方案B实现：实际渲染一次图片获取真实尺寸，确保文本坐标和图片使用相同基准
        
        Args:
            file_path: PDF文件路径
            page_number: 页面编号（从1开始）
            
        Returns:
            包含文本位置列表和页面尺寸信息的字典
        """
        text_items = []
        
        with pdfplumber.open(file_path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return {
                    "text_items": [],
                    "page_dimensions": None
                }
            
            page = pdf.pages[page_number - 1]
            
            # ✅ 获取PDF页面原始尺寸（PDF标准：72 DPI）
            page_width_px_72dpi = page.width  # 72 DPI下的像素尺寸
            page_height_px_72dpi = page.height
            
            # 导入配置以获取实际渲染DPI
            import app.config as config
            render_dpi = config.settings.image_resolution  # 150 DPI
            
            # 【方案B核心改进】实际渲染一次图片，获取真实渲染尺寸
            # 这确保文本坐标转换使用的尺寸与最终显示的图片尺寸完全一致
            try:
                img = page.to_image(resolution=render_dpi)
                actual_width, actual_height = img.size  # 真实渲染尺寸（例如：1275, 1650）
                
                # 计算真实的缩放因子（基于实际渲染尺寸）
                actual_scale_factor_x = actual_width / page_width_px_72dpi
                actual_scale_factor_y = actual_height / page_height_px_72dpi
                
                # 使用真实渲染尺寸（前端将使用这个尺寸计算百分比）
                page_width_px = float(actual_width)
                page_height_px = float(actual_height)
                
                print(f"[PDF文本位置提取] 页面 {page_number}: 真实渲染尺寸 = {actual_width} × {actual_height}px (缩放因子: x={actual_scale_factor_x:.4f}, y={actual_scale_factor_y:.4f})")
            except Exception as e:
                # print(f"[PDF文本位置提取] 警告：无法获取真实渲染尺寸，使用理论计算: {e}")
                # 降级：使用理论计算
                scale_factor = render_dpi / 72.0  # 150/72 ≈ 2.0833
                page_width_px = page_width_px_72dpi * scale_factor
                page_height_px = page_height_px_72dpi * scale_factor
                actual_scale_factor_x = actual_scale_factor_y = scale_factor
            
            # 转换为英寸（用于计算实际DPI）
            page_width_inches = page_width_px_72dpi / 72
            page_height_inches = page_height_px_72dpi / 72
            
            # 使用pdfplumber提取字符级别的位置
            # pdfplumber的坐标系统：原点在左下角，y向上
            # Canvas坐标系统：原点在左上角，y向下
            # 需要转换：y_canvas = page.height - y_pdf
            
            # 提取单词（words包含位置信息）
            words = page.extract_words()
            
            for word in words:
                text = word.get("text", "").strip()
                if text:
                    # PDF坐标（左下角为原点）
                    x0 = word.get("x0", 0)
                    top_pdf = word.get("top", 0)  # PDF坐标系中的top（文本块上边界，y值较大）
                    x1 = word.get("x1", 0)
                    bottom_pdf = word.get("bottom", 0)  # PDF坐标系中的bottom（文本块下边界，y值较小）
                    
                    # 转换为Canvas坐标（左上角为原点）
                    # 关键理解：
                    # - PDF坐标系统：左下角为原点，y向上
                    #   - top_pdf是文本块的上边界（y值较大，接近page.height）
                    #   - bottom_pdf是文本块的下边界（y值较小，接近0）
                    # - Canvas坐标系统：左上角为原点，y向下
                    #   - 矩形的y应该是矩形顶部的y坐标
                    #   - 文本块顶部在PDF中的y = top_pdf（大值）
                    #   - 转换为Canvas：y_top = page.height - top_pdf（小值，接近0）✅
                    
                    # ✅ 正确的转换：使用top_pdf转换为Canvas坐标
                    # 【方案B】使用真实缩放因子进行坐标转换
                    y_canvas_top_72dpi = page_height_px_72dpi - top_pdf
                    width_72dpi = x1 - x0
                    height_72dpi = top_pdf - bottom_pdf
                    
                    # 使用真实的缩放因子缩放到渲染DPI（确保与图片尺寸一致）
                    x = x0 * actual_scale_factor_x
                    y_canvas_top = y_canvas_top_72dpi * actual_scale_factor_y
                    width = width_72dpi * actual_scale_factor_x
                    height = height_72dpi * actual_scale_factor_y
                    
                    # 字体大小
                    font_size = word.get("size", 12)
                    # 使用平均缩放因子缩放字体大小
                    avg_scale_factor = (actual_scale_factor_x + actual_scale_factor_y) / 2
                    
                    text_items.append({
                        "text": text,
                        "position": {
                            "x": round(x, 2),  # 使用真实缩放因子转换（与图片尺寸一致）
                            "y": round(y_canvas_top, 2),  # 使用真实缩放因子转换（与图片尺寸一致）
                            "width": round(width, 2),
                            "height": round(height, 2),
                        },
                        "font_size": round(font_size * avg_scale_factor, 2)
                    })
                    
                    # 调试：对于特定文本，输出详细信息
                    if any(keyword.lower() in text.lower() for keyword in ["metatrader", "tradingview", "algogene"]):
                        y_canvas_bottom = (page_height_px_72dpi - bottom_pdf) * actual_scale_factor_y
                        print(f"[PDF坐标调试] 文本: '{text}'")
                        print(f"  PDF坐标(72 DPI): x0={x0}, x1={x1}, top={top_pdf}, bottom={bottom_pdf}")
                        print(f"  渲染DPI: {render_dpi}, 真实缩放因子: x={actual_scale_factor_x:.4f}, y={actual_scale_factor_y:.4f}")
                        print(f"  真实渲染尺寸: {page_width_px:.2f} × {page_height_px:.2f}px")
                        print(f"  Canvas坐标: x={x:.2f}, y_top={y_canvas_top:.2f}, y_bottom={y_canvas_bottom:.2f}, width={width:.2f}, height={height:.2f}")
                        print(f"  Canvas百分比位置: x={(x/page_width_px*100):.2f}%, y={(y_canvas_top/page_height_px*100):.2f}%")
        
        # 返回文本位置和尺寸信息
        # 【方案B】返回真实渲染尺寸，确保前端百分比计算准确
        return {
            "text_items": text_items,
            "page_dimensions": {
                "width_inches": round(page_width_inches, 2),
                "height_inches": round(page_height_inches, 2),
                "width_pixels": round(page_width_px, 2),  # 真实渲染尺寸（与实际图片完全一致）
                "height_pixels": round(page_height_px, 2),  # 真实渲染尺寸（与实际图片完全一致）
                "width_pixels_72dpi": round(page_width_px_72dpi, 2),  # PDF原始尺寸（72 DPI）
                "height_pixels_72dpi": round(page_height_px_72dpi, 2),  # PDF原始尺寸（72 DPI）
                "dpi": render_dpi,  # 实际渲染DPI（150）
                "scale_factor_x": round(actual_scale_factor_x, 4),  # 真实缩放因子（x方向）
                "scale_factor_y": round(actual_scale_factor_y, 4),  # 真实缩放因子（y方向）
                "is_actual_size": True  # 标记：这是真实渲染尺寸，不是理论计算
            }
        }
    
    def _extract_outline(self, pdf) -> List[Dict[str, Any]]:
        """提取 PDF 目录/大纲结构
        
        Args:
            pdf: PDF 文档对象
            
        Returns:
            目录结构列表
        """
        outline = []
        
        # pdfplumber 可能不支持目录提取，使用简单方法
        # 尝试从前几页提取可能的标题
        try:
            for page_num, page in enumerate(pdf.pages[:5], 1):  # 只检查前5页
                text = page.extract_text()
                if text:
                    # 查找可能是标题的行（通常较短且格式特殊）
                    lines = text.split('\n')[:10]  # 前10行
                    for line in lines:
                        line = line.strip()
                        if line and len(line) < 100 and not line.startswith(' '):
                            outline.append({
                                "title": line,
                                "page": page_num
                            })
                            break
        except:
            pass
        
        return outline

