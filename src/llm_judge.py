"""LLM 判断模块 - 支持 Claude、OpenAI 和 Azure OpenAI"""
import json
import time
from typing import List, Dict, Optional
from .models import PullRequest, LLMJudgment

class LLMJudge:
    """LLM 判断器"""

    def __init__(self, provider: str, api_key: str, model: str,
                 base_url: str = None, max_tokens: int = 2048,
                 api_version: str = None, azure_endpoint: str = None,
                 default_headers: Dict = None, request_timeout: float = 60.0,
                 max_retries: int = 3, retry_backoff: float = 2.0,
                 max_retry_wait: float = 60.0):
        self.provider = provider.lower()
        self.model = model
        self.max_tokens = max_tokens
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_retry_wait = max_retry_wait

        if self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key, timeout=request_timeout)
        elif self.provider == "azure":
            from openai import AzureOpenAI
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version or "2024-02-01",
                azure_endpoint=azure_endpoint,
                default_headers=default_headers or {},
                timeout=request_timeout
            )
        elif self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=request_timeout)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def judge_chain(self, prs: List[PullRequest], repo: str) -> LLMJudgment:
        """判断 PR 链质量"""
        prompt = self._build_prompt(prs, repo)
        text = self._call_model_with_retry(prompt)

        result = self._parse_response(text)
        return result

    def _call_model_with_retry(self, prompt: str) -> str:
        """调用模型并在瞬时错误时重试"""
        for attempt in range(1, self.max_retries + 2):
            try:
                if self.provider == "anthropic":
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=self.max_tokens,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return response.content[0].text

                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ],
                    stream=False
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt <= self.max_retries and self._is_retryable_exception(e):
                    wait_seconds = self._get_retry_wait(e, attempt)
                    print(
                        f"LLM transient error ({type(e).__name__}), retrying in "
                        f"{wait_seconds:.1f}s ({attempt}/{self.max_retries})"
                    )
                    time.sleep(wait_seconds)
                    continue
                raise

    def _build_prompt(self, prs: List[PullRequest], repo: str) -> str:
        """构建 LLM prompt (英文)"""
        prompt = f"""You are a GitHub PR chain quality evaluator. Analyze whether the following PR chain forms a reasonable evolution chain.

## PR Chain Information
Repository: {repo}
Number of PRs: {len(prs)}

"""
        for i, pr in enumerate(prs, 1):
            title = self._normalize_text(pr.title)
            body = self._normalize_text(pr.body)
            user = self._normalize_text(pr.user, default="unknown")
            labels = ', '.join(pr.labels) if pr.labels else 'None'
            prompt += f"""### PR #{i}: {pr.number}
- Title: {title}
- Author: {user}
- Created: {pr.created_at.strftime('%Y-%m-%d')}
- Merged: {pr.merged_at.strftime('%Y-%m-%d') if pr.merged_at else 'N/A'}
- Labels: {labels}
- Description: {body[:200]}...
- Changes: +{pr.additions} -{pr.deletions} ({pr.changed_files} files)

"""

        prompt += """## Analysis Dimensions (0-10 points each)
1. Topic Consistency: Do these PRs revolve around the same feature/module?
2. Logical Relevance: Is there a clear dependency or evolution relationship between PRs?
3. Temporal Reasonableness: Are the time intervals and order reasonable?
4. Author Consistency: If multiple authors, is the collaboration reasonable?

## Output JSON Format:
```json
{
    "is_valid_chain": true,
    "confidence": 0.85,
    "scores": {
        "topic_consistency": 8,
        "logical_relevance": 7,
        "temporal_reasonableness": 9,
        "author_consistency": 6
    },
    "overall_score": 7.5,
    "reasoning": "Brief explanation",
    "evolution_pattern": "incremental_enhancement",
    "function_types": ["ENH"],
    "issues": []
}
```

evolution_pattern options: incremental_enhancement/iterative_bugfix/long_term_refactoring/collaborative_development
function_types options: ENH/BUG/MAINT/DOC/TST/PERF
"""
        return prompt

    def _parse_response(self, text: str) -> LLMJudgment:
        """解析 LLM 响应"""
        if text is None:
            raise ValueError("LLM returned empty content")

        start = text.find('{')
        end = text.rfind('}') + 1
        if start == -1 or end <= start:
            raise ValueError(f"LLM did not return JSON: {text[:300]}")

        json_str = text[start:end]
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError(f"LLM returned non-object JSON: {json_str[:300]}")

        return LLMJudgment(
            is_valid_chain=data['is_valid_chain'],
            confidence=data['confidence'],
            overall_score=data['overall_score'],
            scores=data['scores'],
            reasoning=data['reasoning'],
            evolution_pattern=data['evolution_pattern'],
            function_types=data['function_types'],
            issues=data.get('issues', [])
        )

    def _normalize_text(self, value: Optional[str], default: str = "") -> str:
        """将可能为 None 的文本字段归一化为字符串"""
        if value is None:
            return default
        if isinstance(value, str):
            return value
        return str(value)

    def _is_retryable_exception(self, error: Exception) -> bool:
        """判断异常是否值得重试"""
        status_code = getattr(error, "status_code", None)
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True

        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        if response_status in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True

        name = type(error).__name__.lower()
        message = str(error).lower()
        retry_keywords = [
            "timeout", "timed out", "rate limit", "too many requests",
            "connection", "tempor", "overloaded", "unavailable",
            "internal server error", "server error", "bad gateway", "gateway timeout"
        ]

        return (
            "timeout" in name or
            "ratelimit" in name or
            "connection" in name or
            any(keyword in message for keyword in retry_keywords)
        )

    def _get_retry_wait(self, error: Exception, attempt: int) -> float:
        """计算重试等待时间"""
        headers = getattr(error, "headers", None)
        response = getattr(error, "response", None)
        if headers is None and response is not None:
            headers = getattr(response, "headers", None)

        if headers:
            retry_after = headers.get("retry-after") or headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.max_retry_wait)
                except ValueError:
                    pass

        return min(self.retry_backoff * (2 ** max(attempt - 1, 0)), self.max_retry_wait)
