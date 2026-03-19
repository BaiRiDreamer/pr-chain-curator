"""LLM 判断模块 - 支持 Claude、OpenAI 和 Azure OpenAI"""
import json
from typing import List, Dict, Optional
from .models import PullRequest, LLMJudgment

class LLMJudge:
    """LLM 判断器"""

    def __init__(self, provider: str, api_key: str, model: str,
                 base_url: str = None, max_tokens: int = 2048,
                 api_version: str = None, azure_endpoint: str = None,
                 default_headers: Dict = None):
        self.provider = provider.lower()
        self.model = model
        self.max_tokens = max_tokens

        if self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        elif self.provider == "azure":
            from openai import AzureOpenAI
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version or "2024-02-01",
                azure_endpoint=azure_endpoint,
                default_headers=default_headers or {}
            )
        elif self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def judge_chain(self, prs: List[PullRequest], repo: str) -> LLMJudgment:
        """判断 PR 链质量"""
        prompt = self._build_prompt(prs, repo)
        if self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
        else:
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
            text = response.choices[0].message.content

        result = self._parse_response(text)
        return result

    def _build_prompt(self, prs: List[PullRequest], repo: str) -> str:
        """构建 LLM prompt (英文)"""
        prompt = f"""You are a GitHub PR chain quality evaluator. Analyze whether the following PR chain forms a reasonable evolution chain.

## PR Chain Information
Repository: {repo}
Number of PRs: {len(prs)}

"""
        for i, pr in enumerate(prs, 1):
            prompt += f"""### PR #{i}: {pr.number}
- Title: {pr.title}
- Author: {pr.user}
- Created: {pr.created_at.strftime('%Y-%m-%d')}
- Merged: {pr.merged_at.strftime('%Y-%m-%d') if pr.merged_at else 'N/A'}
- Labels: {', '.join(pr.labels) if pr.labels else 'None'}
- Description: {pr.body[:200]}...
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
        start = text.find('{')
        end = text.rfind('}') + 1
        json_str = text[start:end]
        data = json.loads(json_str)

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
