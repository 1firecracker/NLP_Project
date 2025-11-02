"""图片渲染工具：将PDF和PPTX转换为图片"""
import os
import sys
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta
from PIL import Image
import pdfplumber


class ImageRenderer:
    """图片渲染器，支持PDF和PPTX转换为图片"""
    
    def __init__(self, cache_dir: str, resolution: int = 150, cache_expiry_hours: int = 24):
        """
        Args:
            cache_dir: 图片缓存目录
            resolution: 图片分辨率（DPI）
            cache_expiry_hours: 缓存过期时间（小时）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.resolution = resolution
        self.cache_expiry_hours = cache_expiry_hours
    
    def _get_cache_path(self, file_id: str, slide_number: int, file_extension: str, is_thumbnail: bool = False) -> Path:
        """获取缓存文件路径
        
        Args:
            file_id: 文件ID
            slide_number: 幻灯片/页面编号
            file_extension: 文件扩展名
            is_thumbnail: 是否为缩略图
        """
        suffix = "_thumb" if is_thumbnail else ""
        return self.cache_dir / file_extension / file_id / f"slide_{slide_number}{suffix}.png"
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """检查缓存是否有效
        
        Args:
            cache_path: 缓存文件路径
            
        Returns:
            缓存是否有效（存在且未过期）
        """
        if not cache_path.exists():
            return False
        
        # 检查是否过期
        file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        expiry_time = datetime.now() - timedelta(hours=self.cache_expiry_hours)
        
        return file_time > expiry_time
    
    def render_pdf_page(
        self,
        file_path: str,
        page_number: int,
        file_id: str,
        use_cache: bool = True,
        is_thumbnail: bool = False
    ) -> Optional[Path]:
        """渲染PDF页面为图片
        
        Args:
            file_path: PDF文件路径
            page_number: 页面编号（从1开始）
            file_id: 文件ID（用于缓存路径）
            use_cache: 是否使用缓存
            is_thumbnail: 是否为缩略图
            
        Returns:
            图片文件路径（如果成功）
        """
        # 计算缓存路径
        cache_path = self._get_cache_path(file_id, page_number, "pdf", is_thumbnail)
        
        # 检查缓存
        if use_cache and self._is_cache_valid(cache_path):
            return cache_path
        
        try:
            # 渲染PDF页面
            with pdfplumber.open(file_path) as pdf:
                if page_number < 1 or page_number > len(pdf.pages):
                    return None
                
                page = pdf.pages[page_number - 1]
                
                # 生成图片
                if is_thumbnail:
                    # 缩略图使用较低分辨率
                    img = page.to_image(resolution=72)
                else:
                    img = page.to_image(resolution=self.resolution)
                
                # 确保缓存目录存在
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 保存图片
                img.save(cache_path, format="PNG", optimize=True)
                
                return cache_path
        except Exception as e:
            print(f"Error rendering PDF page {page_number}: {e}")
            return None
    
    def render_pptx_slide(
        self,
        file_path: str,
        slide_number: int,
        file_id: str,
        use_cache: bool = True,
        is_thumbnail: bool = False
    ) -> Optional[Path]:
        """渲染PPTX幻灯片为图片（Windows使用COM接口）
        
        Args:
            file_path: PPTX文件路径
            slide_number: 幻灯片编号（从1开始）
            file_id: 文件ID（用于缓存路径）
            use_cache: 是否使用缓存
            is_thumbnail: 是否为缩略图
            
        Returns:
            图片文件路径（如果成功）
        """
        # 计算缓存路径
        cache_path = self._get_cache_path(file_id, slide_number, "pptx", is_thumbnail)
        
        # 检查缓存
        if use_cache and self._is_cache_valid(cache_path):
            return cache_path
        
        # Windows环境：使用COM接口
        if sys.platform == "win32":
            try:
                import comtypes.client
                
                # 创建PowerPoint应用对象
                ppt_app = comtypes.client.CreateObject("PowerPoint.Application")
                
                # 尝试隐藏窗口（某些PowerPoint版本或设置可能不允许，捕获异常）
                try:
                    ppt_app.Visible = False
                except Exception:
                    # 如果隐藏失败，尝试最小化窗口
                    try:
                        ppt_app.WindowState = 2  # ppWindowMinimized = 2
                    except Exception:
                        # 如果都失败，继续执行（窗口会显示但不影响功能）
                        pass
                
                # 打开演示文稿
                presentation = ppt_app.Presentations.Open(str(Path(file_path).absolute()))
                
                try:
                    # 获取幻灯片（slide_number从1开始，COM中也是从1开始）
                    if slide_number < 1 or slide_number > presentation.Slides.Count:
                        return None
                    
                    slide = presentation.Slides[slide_number]
                    
                    # 计算导出分辨率
                    # PowerPoint导出使用像素，150 DPI ≈ 每英寸150像素
                    # 标准幻灯片尺寸：10英寸宽 × 7.5英寸高
                    if is_thumbnail:
                        # 缩略图：较小尺寸
                        width = 200
                        height = 150
                    else:
                        # 全尺寸：按150 DPI计算（10*150 = 1500像素）
                        width = int(10 * self.resolution)
                        height = int(7.5 * self.resolution)
                    
                    # 确保缓存目录存在
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 临时文件路径（使用绝对路径）
                    temp_path = cache_path.parent / f"temp_{slide_number}_{file_id}.png"
                    
                    # 导出为PNG（使用绝对路径）
                    slide.Export(
                        str(temp_path.absolute()),
                        "PNG",
                        width,
                        height
                    )
                    
                    # 移动文件到缓存路径
                    if temp_path.exists():
                        # 如果目标文件已存在，先删除
                        if cache_path.exists():
                            cache_path.unlink()
                        temp_path.replace(cache_path)
                        # 清理临时文件（如果还存在）
                        if temp_path.exists():
                            temp_path.unlink()
                    
                    return cache_path if cache_path.exists() else None
                    
                finally:
                    # 关闭演示文稿和应用
                    try:
                        presentation.Close()
                    except:
                        pass
                    try:
                        # 退出PowerPoint应用
                        ppt_app.Quit()
                    except:
                        pass
                    # 释放COM对象
                    try:
                        del presentation
                    except:
                        pass
                    try:
                        del ppt_app
                    except:
                        pass
            
            except ImportError:
                print("Warning: comtypes not installed. PPTX rendering requires 'pip install comtypes'")
                return None
            except Exception as e:
                print(f"Error rendering PPTX slide {slide_number}: {e}")
                return None
        else:
            # Linux/Mac环境：使用LibreOffice
            return self._render_pptx_with_libreoffice(
                file_path, slide_number, file_id, cache_path, is_thumbnail
            )
    
    def _render_pptx_with_libreoffice(
        self,
        file_path: str,
        slide_number: int,
        file_id: str,
        cache_path: Path,
        is_thumbnail: bool = False
    ) -> Optional[Path]:
        """使用LibreOffice渲染PPTX幻灯片为图片（Linux/Mac）
        
        Args:
            file_path: PPTX文件路径
            slide_number: 幻灯片编号（从1开始）
            file_id: 文件ID
            cache_path: 缓存路径
            is_thumbnail: 是否为缩略图
            
        Returns:
            图片文件路径（如果成功）
        """
        import subprocess
        import tempfile
        import shutil
        
        # 检查LibreOffice是否安装
        libreoffice_cmd = shutil.which("libreoffice")
        if not libreoffice_cmd:
            print("Warning: LibreOffice not found. Please install LibreOffice for PPTX rendering on Linux/Mac.")
            print("Install: Ubuntu/Debian: sudo apt-get install libreoffice")
            print("        CentOS/RHEL: sudo yum install libreoffice")
            print("        macOS: brew install --cask libreoffice")
            return None
        
        try:
            # 创建临时目录用于LibreOffice输出
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_output_dir = Path(temp_dir)
                
                # LibreOffice命令：转换为PDF（因为LibreOffice不能直接导出单页PNG）
                # 注意：LibreOffice的--convert-to png会将所有幻灯片导出为单独的PNG文件
                # 文件命名格式：原始文件名_slide编号.png（从0开始）
                cmd = [
                    libreoffice_cmd,
                    "--headless",
                    "--convert-to", "png",
                    "--outdir", str(temp_output_dir),
                    str(Path(file_path).absolute())
                ]
                
                # 执行转换
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60,  # 60秒超时
                    check=False
                )
                
                if result.returncode != 0:
                    print(f"LibreOffice conversion failed: {result.stderr.decode('utf-8', errors='ignore')}")
                    return None
                
                # 查找生成的PNG文件
                # LibreOffice会将PPTX转换为多个PNG文件，命名规则：
                # 如果原文件是 "file.pptx"，生成的可能是：
                # - file_1.png, file_2.png, ... (取决于幻灯片数量)
                # 或者: file.png (第一张幻灯片)
                # 或者: file-0.png, file-1.png, ...
                
                # 尝试多种命名规则
                base_name = Path(file_path).stem
                possible_patterns = [
                    f"{base_name}_{slide_number}.png",  # file_1.png
                    f"{base_name}-{slide_number - 1}.png",  # file-0.png (从0开始)
                    f"{base_name}.png",  # file.png (第一张幻灯片)
                ]
                
                # 如果slide_number是1，也可能就是文件名.png
                if slide_number == 1:
                    possible_patterns.insert(0, f"{base_name}.png")
                
                # 搜索所有PNG文件，找到对应幻灯片的
                png_files = list(temp_output_dir.glob("*.png"))
                
                if not png_files:
                    print(f"No PNG files generated by LibreOffice in {temp_output_dir}")
                    return None
                
                # 如果只有一张幻灯片，直接使用第一个文件
                if len(png_files) == 1 and slide_number == 1:
                    source_file = png_files[0]
                elif slide_number <= len(png_files):
                    # 按文件名排序，取第slide_number-1个（因为数组从0开始）
                    png_files_sorted = sorted(png_files, key=lambda x: x.name)
                    source_file = png_files_sorted[slide_number - 1]
                else:
                    print(f"Slide {slide_number} not found. Only {len(png_files)} slides generated.")
                    return None
                
                # 确保缓存目录存在
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 如果目标文件已存在，先删除
                if cache_path.exists():
                    cache_path.unlink()
                
                # 如果是缩略图，需要调整大小
                if is_thumbnail and source_file.exists():
                    from PIL import Image
                    with Image.open(source_file) as img:
                        # 缩略图尺寸
                        img.thumbnail((200, 150), Image.Resampling.LANCZOS)
                        img.save(cache_path, format="PNG", optimize=True)
                else:
                    # 直接复制文件
                    shutil.copy2(source_file, cache_path)
                
                return cache_path if cache_path.exists() else None
                
        except subprocess.TimeoutExpired:
            print(f"LibreOffice conversion timeout after 60s for slide {slide_number}")
            return None
        except FileNotFoundError:
            print("LibreOffice not found. Please install LibreOffice.")
            return None
        except Exception as e:
            print(f"Error rendering PPTX slide {slide_number} with LibreOffice: {e}")
            return None
    
    def render_slide(
        self,
        file_path: str,
        slide_number: int,
        file_id: str,
        file_extension: str,
        use_cache: bool = True,
        is_thumbnail: bool = False
    ) -> Optional[Path]:
        """渲染幻灯片/页面为图片（统一接口）
        
        Args:
            file_path: 文件路径
            slide_number: 幻灯片/页面编号（从1开始）
            file_id: 文件ID
            file_extension: 文件扩展名（pdf/pptx）
            use_cache: 是否使用缓存
            is_thumbnail: 是否为缩略图
            
        Returns:
            图片文件路径
        """
        if file_extension.lower() == "pdf":
            return self.render_pdf_page(file_path, slide_number, file_id, use_cache, is_thumbnail)
        elif file_extension.lower() == "pptx":
            return self.render_pptx_slide(file_path, slide_number, file_id, use_cache, is_thumbnail)
        else:
            return None
    
    def get_image_path(
        self,
        file_path: str,
        slide_number: int,
        file_id: str,
        file_extension: str,
        use_cache: bool = True,
        is_thumbnail: bool = False
    ) -> Optional[Path]:
        """获取图片路径（如果不存在则生成）
        
        Args:
            file_path: 原始文件路径
            slide_number: 幻灯片/页面编号
            file_id: 文件ID
            file_extension: 文件扩展名
            use_cache: 是否使用缓存
            is_thumbnail: 是否为缩略图
            
        Returns:
            图片文件路径
        """
        cache_path = self._get_cache_path(file_id, slide_number, file_extension, is_thumbnail)
        
        # 如果缓存有效，直接返回
        if use_cache and self._is_cache_valid(cache_path):
            return cache_path
        
        # 否则渲染并返回
        return self.render_slide(file_path, slide_number, file_id, file_extension, use_cache, is_thumbnail)
    
    def clear_cache(self, file_id: Optional[str] = None):
        """清除缓存
        
        Args:
            file_id: 文件ID（如果指定，只清除该文件的缓存；否则清除所有）
        """
        if file_id:
            # 清除指定文件的缓存
            for ext in ["pdf", "pptx"]:
                cache_dir = self.cache_dir / ext / file_id
                if cache_dir.exists():
                    import shutil
                    shutil.rmtree(cache_dir)
        else:
            # 清除所有缓存
            if self.cache_dir.exists():
                import shutil
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)

