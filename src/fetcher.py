"""GitHub API 封装"""
import time
from email.utils import parsedate_to_datetime
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .cache import FileCache
from .github_token_pool import GitHubTokenPool, GitHubTokenState
from .models import PullRequest


class GitHubFetcher:
    """GitHub API 获取器"""

    def __init__(self, tokens: List[str], cache_dir: str, rate_limit_delay: float = 0.5,
                 request_timeout: float = 30.0, max_retries: int = 3,
                 retry_backoff: float = 2.0, max_retry_wait: float = 60.0):
        self.token_pool = GitHubTokenPool(tokens)
        self.cache = FileCache(cache_dir)
        self.rate_limit_delay = rate_limit_delay
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_retry_wait = max_retry_wait

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
                    pr = future.result()
                    if pr is not None:
                        results[pr_id] = pr
                except Exception as e:
                    print(f"Error fetching {pr_id}: {e}")
        return results

    def fetch_pr(self, pr_id: str, fetch_files: bool = False) -> Optional[PullRequest]:
        """获取单个 PR 信息"""
        cache_key = f"{pr_id}_{'with_files' if fetch_files else 'basic'}"
        cached = self.cache.get(cache_key)
        if cached:
            return self._parse_pr(cached, pr_id.split('#')[0])

        repo, number = self._parse_pr_id(pr_id)
        data = self._call_api(f"/repos/{repo}/pulls/{number}")
        if not data:
            return None

        if fetch_files:
            files_data = self._call_api(f"/repos/{repo}/pulls/{number}/files")
            data['files'] = [f['filename'] for f in files_data] if files_data else []

        self.cache.set(cache_key, data)
        return self._parse_pr(data, repo)

    def _call_api(self, endpoint: str) -> Optional[Dict]:
        """调用 GitHub API"""
        url = f"https://api.github.com{endpoint}"
        for attempt in range(1, self.max_retries + 2):
            token_state = self.token_pool.acquire()
            try:
                response = requests.get(
                    url,
                    headers=self._build_headers(token_state),
                    timeout=self.request_timeout
                )
                remaining = self._parse_int_header(response.headers.get("X-RateLimit-Remaining"))
                reset_at = self._parse_reset_at(response.headers.get("X-RateLimit-Reset"))

                if response.status_code == 200:
                    self.token_pool.release(
                        token_state,
                        min_delay=self.rate_limit_delay,
                        remaining=remaining,
                        reset_at=reset_at
                    )
                    return response.json()

                if self._should_retry_response(response) and attempt <= self.max_retries:
                    wait_seconds = self._get_retry_wait(response, attempt)
                    print(
                        f"GitHub API transient error {response.status_code} on {endpoint}, "
                        f"retrying in {wait_seconds:.1f}s ({attempt}/{self.max_retries})"
                    )
                    if self._is_rate_limit_response(response):
                        self.token_pool.defer(
                            token_state,
                            wait_seconds,
                            remaining=remaining,
                            reset_at=reset_at
                        )
                    else:
                        self.token_pool.release(
                            token_state,
                            min_delay=self.rate_limit_delay,
                            remaining=remaining,
                            reset_at=reset_at
                        )
                        time.sleep(wait_seconds)
                    continue

                self.token_pool.release(
                    token_state,
                    min_delay=self.rate_limit_delay,
                    remaining=remaining,
                    reset_at=reset_at
                )
                print(f"GitHub API error {response.status_code}: {endpoint}")
                return None
            except requests.exceptions.Timeout as e:
                self.token_pool.release(token_state, min_delay=self.rate_limit_delay)
                if attempt <= self.max_retries:
                    wait_seconds = self._get_retry_wait(None, attempt)
                    print(
                        f"GitHub API timeout on {endpoint}, retrying in {wait_seconds:.1f}s "
                        f"({attempt}/{self.max_retries})"
                    )
                    time.sleep(wait_seconds)
                    continue
                print(f"GitHub API timeout: {endpoint}: {e}")
            except requests.exceptions.ConnectionError as e:
                self.token_pool.release(token_state, min_delay=self.rate_limit_delay)
                if attempt <= self.max_retries:
                    wait_seconds = self._get_retry_wait(None, attempt)
                    print(
                        f"GitHub API connection error on {endpoint}, retrying in {wait_seconds:.1f}s "
                        f"({attempt}/{self.max_retries})"
                    )
                    time.sleep(wait_seconds)
                    continue
                print(f"GitHub API connection error: {endpoint}: {e}")
            except requests.exceptions.RequestException as e:
                self.token_pool.release(token_state, min_delay=self.rate_limit_delay)
                if attempt <= self.max_retries and self._is_retryable_request_exception(e):
                    wait_seconds = self._get_retry_wait(None, attempt)
                    print(
                        f"GitHub API request error on {endpoint}, retrying in {wait_seconds:.1f}s "
                        f"({attempt}/{self.max_retries})"
                    )
                    time.sleep(wait_seconds)
                    continue
                print(f"GitHub API request error: {endpoint}: {e}")
                return None
        return None

    def _should_retry_response(self, response: requests.Response) -> bool:
        """判断响应是否适合重试"""
        if response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            body = response.text.lower()
            if remaining == "0" or "rate limit" in body:
                return True
        return False

    def _is_rate_limit_response(self, response: requests.Response) -> bool:
        """判断响应是否为 rate limit 问题。"""
        if response.status_code == 429:
            return True
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            body = response.text.lower()
            return remaining == "0" or "rate limit" in body
        return False

    def _is_retryable_request_exception(self, error: requests.exceptions.RequestException) -> bool:
        """判断 requests 异常是否适合重试"""
        message = str(error).lower()
        retry_keywords = [
            "timed out", "timeout", "tempor", "connection reset",
            "connection aborted", "remote end closed", "503", "502", "504"
        ]
        return any(keyword in message for keyword in retry_keywords)

    def _get_retry_wait(self, response: Optional[requests.Response], attempt: int) -> float:
        """计算重试等待时间"""
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.max_retry_wait)
                except ValueError:
                    try:
                        retry_at = parsedate_to_datetime(retry_after).timestamp()
                        return min(max(retry_at - time.time(), 1.0), self.max_retry_wait)
                    except (TypeError, ValueError, OverflowError):
                        pass

            rate_limit_reset = response.headers.get("X-RateLimit-Reset")
            if rate_limit_reset:
                try:
                    wait_seconds = float(rate_limit_reset) - time.time()
                    return min(max(wait_seconds, 1.0), self.max_retry_wait)
                except ValueError:
                    pass

        return min(self.retry_backoff * (2 ** max(attempt - 1, 0)), self.max_retry_wait)

    def _build_headers(self, token_state: GitHubTokenState) -> Dict[str, str]:
        """构建请求头。"""
        return {"Authorization": f"token {token_state.token}"}

    def _parse_int_header(self, value: Optional[str]) -> Optional[int]:
        """解析整型 header。"""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_reset_at(self, value: Optional[str]) -> Optional[float]:
        """解析 rate limit reset 时间。"""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
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
