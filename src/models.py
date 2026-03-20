"""数据模型定义"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class PullRequest:
    """PR 信息"""
    repo: str
    number: int
    title: str
    body: str
    created_at: datetime
    merged_at: Optional[datetime]
    user: str
    labels: List[str]
    changed_files: int
    additions: int
    deletions: int
    files: List[str] = field(default_factory=list)

    @property
    def pr_id(self) -> str:
        return f"{self.repo}#{self.number}"

@dataclass
class LLMJudgment:
    """LLM 判断结果"""
    is_valid_chain: bool
    confidence: float
    overall_score: float
    scores: Dict[str, int]
    reasoning: str
    evolution_pattern: str
    function_types: List[str]
    issues: List[str]

@dataclass
class FilterResult:
    """筛选结果"""
    chain_id: str
    original_chain: List[str]
    status: str  # approved/rejected
    quality_score: float
    llm_judgment: Optional[LLMJudgment]
    issues: List[str]
    file_overlap_rate: Optional[float] = None
