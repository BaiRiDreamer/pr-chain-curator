"""缓存管理"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from tempfile import NamedTemporaryFile

class FileCache:
    """文件系统缓存"""

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        safe_key = key.replace('/', '_').replace('#', '_')
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[Dict[Any, Any]]:
        """获取缓存"""
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            with open(cache_path, 'r') as f:
                return json.load(f)
        return None

    def set(self, key: str, value: Dict[Any, Any]):
        """设置缓存"""
        cache_path = self._get_cache_path(key)
        with NamedTemporaryFile('w', dir=self.cache_dir, delete=False, encoding='utf-8') as tmp_file:
            json.dump(value, tmp_file, indent=2)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            temp_path = Path(tmp_file.name)

        os.replace(temp_path, cache_path)

    def clear(self):
        """清空缓存"""
        for file in self.cache_dir.glob("*.json"):
            file.unlink()
