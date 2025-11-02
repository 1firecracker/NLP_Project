"""文件存储管理"""
import uuid
import shutil
from pathlib import Path
from typing import Optional, Dict
import app.config as config


class FileManager:
    """文件管理器，负责文件的保存、查询、删除"""
    
    def __init__(self):
        self.base_upload_dir = Path(config.settings.upload_dir)
        self.base_upload_dir.mkdir(parents=True, exist_ok=True)
    
    def save_file(self, conversation_id: str, file_content: bytes, original_filename: str) -> Dict:
        """保存文件
        
        Args:
            conversation_id: 对话ID
            file_content: 文件内容（字节）
            original_filename: 原始文件名
            
        Returns:
            包含文件信息的字典
        """
        # 生成唯一文件ID
        file_id = str(uuid.uuid4())
        
        # 获取文件扩展名
        original_path = Path(original_filename)
        extension = original_path.suffix.lower()
        
        # 构建保存路径
        conversation_dir = Path(config.settings.conversations_dir) / conversation_id / "documents"
        conversation_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存文件名使用 file_id + 扩展名
        saved_filename = f"{file_id}{extension}"
        file_path = conversation_dir / saved_filename
        
        # 保存文件
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        file_size = len(file_content)
        
        return {
            "file_id": file_id,
            "conversation_id": conversation_id,
            "original_filename": original_filename,
            "saved_filename": saved_filename,
            "file_path": str(file_path),
            "file_size": file_size,
            "file_extension": extension.lstrip('.')
        }
    
    def get_file_path(self, conversation_id: str, file_id: str) -> Optional[Path]:
        """获取文件路径
        
        Args:
            conversation_id: 对话ID
            file_id: 文件ID
            
        Returns:
            文件路径，如果不存在返回 None
        """
        conversation_dir = Path(config.settings.conversations_dir) / conversation_id / "documents"
        
        # 查找匹配的文件
        for file_path in conversation_dir.glob(f"{file_id}.*"):
            if file_path.is_file():
                return file_path
        
        return None
    
    def delete_file(self, conversation_id: str, file_id: str) -> bool:
        """删除文件
        
        Args:
            conversation_id: 对话ID
            file_id: 文件ID
            
        Returns:
            是否删除成功
        """
        file_path = self.get_file_path(conversation_id, file_id)
        
        if file_path and file_path.exists():
            file_path.unlink()
            return True
        
        return False
    
    def list_files(self, conversation_id: str) -> list:
        """列出对话的所有文件
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            文件信息列表
        """
        conversation_dir = Path(config.settings.conversations_dir) / conversation_id / "documents"
        
        if not conversation_dir.exists():
            return []
        
        files = []
        for file_path in conversation_dir.iterdir():
            if file_path.is_file():
                # 提取 file_id（文件名去掉扩展名）
                file_id = file_path.stem
                files.append({
                    "file_id": file_id,
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size,
                    "file_extension": file_path.suffix.lstrip('.')
                })
        
        return files

