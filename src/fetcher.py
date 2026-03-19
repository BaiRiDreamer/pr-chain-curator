"""GitHub API 封装"""
import requests
import time
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .cache import FileCache
from .models import PullRequest

class GitHubFetcher:
    """GitHub API 获取器"""

    def __init__(self, token: str, cache_dir: str, rate_limit_delay: float = 0.5):
        self.token = token
        self.headers = {"Authorization": f"token {token}"}
        self.cache = FileCache(cache_dir)
        self.rate_limit_delay = rate_limit_delay

    def fetch_pr_batch(self, pr_ids: List[str], max_workers: int = 20,
                       fetch_files: bool = False) -> Dict[str, PullRequest]:
        """并发获取多个 PR"""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.fetch_pr, pr_id, fetch_files): pr_id
                for pr_id in pr_ids
            }
            for future in as_completed(futures):
                pr_id = futures[future]
                try:
                    results[pr_id] = future.result()
                except Exception as e:
                    print(f"Error fetching {pr_id}: {e}")
        return results

    def fetch_pr(self, pr_id: str, fetch_files: bool = False) -> Optional[PullRequest]:
        """获取单个 PR 信息"""
        # 检查缓存
        cache_key = f"{pr_id}_{'with_files' if fetch_files else 'basic'}"
        cached = self.cache.get(cache_key)
        if cached:
            return self._parse_pr(cached, pr_id.split('#')[0])

        # 调用 API
        repo, number = self._parse_pr_id(pr_id)
        data = self._call_api(f"/repos/{repo}/pulls/{number}")
        if not data:
            return None

        # 获取文件列表
        if fetch_files:
            files_data = self._call_api(f"/repos/{repo}/pulls/{number}/files")
            data['files'] = [f['filename'] for f in files_data] if files_data else []

        # 缓存
        self.cache.set(cache_key, data)
        return self._parse_pr(data, repo)

    def _call_api(self, endpoint: str) -> Optional[Dict]:
        """调用 GitHub API"""
        url = f"https://api.github.com{endpoint}"
        try:
            response = requests.get(url, headers=self.headers)
            time.sleep(self.rate_limit_delay)
            if response.status_code == 200:
                return response.json()
            print(f"API error {response.status_code}: {endpoint}")
        except Exception as e:
            print(f"Request error: {e}")
        return None

    def _parse_pr_id(self, pr_id: str) -> tuple:
        """解析 PR ID"""
        parts = pr_id.split('#')
        return parts[0], int(parts[1])

    def _parse_pr(self, data: Dict, repo: str) -> PullRequest:
        """解析 PR 数据"""
        return PullRequest(
            repo=repo,
            number=data['number'],
            title=data.get('title') or '',
            body=data.get('body') or '',
            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00')),
            merged_at=datetime.fromisoformat(data['merged_at'].replace('Z', '+00:00')) if data.get('merged_at') else None,
            user=data['user']['login'],
            labels=[l['name'] for l in data.get('labels', [])],
            changed_files=data.get('changed_files', 0),
            additions=data.get('additions', 0),
            deletions=data.get('deletions', 0),
            files=data.get('files', [])
        )
