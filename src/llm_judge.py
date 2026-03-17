"""LLM 判断模块"""
import json
import anthropic
from typing import List
from .models import PullRequest, LLMJudgment

class LLMJudge:
    """LLM 判断器"""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022", max_tokens: int = 2048):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def judge_chain(self, prs: List[PullRequest], repo: str) -> LLMJudgment:
        """判断 PR 链质量"""
        prompt = self._build_prompt(prs, repo)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        # 解析响应
        text = response.content[0].text
        result = self._parse_response(text)
        return result

    def _build_prompt(self, prs: List[PullRequest], repo: str) -> str:
        """构建 LLM prompt"""
        prompt = f"""你是 GitHub PR 链质量评估专家。分析以下 PR 链是否构成合理的演化链。

## PR 链信息
仓库: {repo}
PR 数量: {len(prs)}

"""
        for i, pr in enumerate(prs, 1):
            prompt += f"""### PR #{i}: {pr.number}
- 标题: {pr.title}
- 作者: {pr.user}
- 创建: {pr.created_at.strftime('%Y-%m-%d')}
- 合并: {pr.merged_at.strftime('%Y-%m-%d') if pr.merged_at else 'N/A'}
- 标签: {', '.join(pr.labels) if pr.labels else 'None'}
- 描述: {pr.body[:200]}...
- 变更: +{pr.additions} -{pr.deletions} ({pr.changed_files} 文件)

"""

        prompt += """## 分析维度 (0-10分)
1. 主题一致性: PR 是否围绕同一功能/模块?
2. 逻辑关联性: PR 之间是否有依赖/演化关系?
3. 时间合理性: 时间间隔和顺序是否合理?
4. 作者一致性: 多作者是否合理?

## 输出 JSON:
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
    "reasoning": "简要理由",
    "evolution_pattern": "incremental_enhancement",
    "function_types": ["ENH"],
    "issues": []
}
```

evolution_pattern 选项: incremental_enhancement/iterative_bugfix/long_term_refactoring/collaborative_development
function_types 选项: ENH/BUG/MAINT/DOC/TST/PERF
"""
        return prompt

    def _parse_response(self, text: str) -> LLMJudgment:
        """解析 LLM 响应"""
        # 提取 JSON
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
