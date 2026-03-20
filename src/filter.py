"""筛选器模块"""
from typing import Iterator, List, Dict, Tuple, Optional
from .chain_identity import build_chain_id
from .models import PullRequest, FilterResult, LLMJudgment
from .fetcher import GitHubFetcher
from .llm_judge import LLMJudge

class ChainFilter:
    """PR 链筛选器"""

    def __init__(self, fetcher: GitHubFetcher, llm_judge: LLMJudge, config: Dict):
        self.fetcher = fetcher
        self.llm_judge = llm_judge
        self.config = config
        self.max_workers = config['github'].get('max_workers', 20)

    def filter_chains(self, chains: List[List[str]]) -> List[FilterResult]:
        """筛选 PR 链"""
        return list(self.iter_filter_chains(chains))

    def iter_filter_chains(self, chains: List[List[str]]) -> Iterator[FilterResult]:
        """流式筛选 PR 链，逐条返回结果"""
        for chain in chains:
            chain_id = build_chain_id(chain)
            yield self.filter_chain(chain_id, chain)

    def filter_chain(self, chain_id: str, chain: List[str]) -> FilterResult:
        """筛选单条 PR 链"""
        return self._filter_single_chain(chain_id, chain)

    def _filter_single_chain(self, chain_id: str, chain: List[str]) -> FilterResult:
        """筛选单条 PR 链"""
        input_chain = list(chain)

        # 预筛选
        passed, reason = self._pre_filter(input_chain)
        if not passed:
            return FilterResult(
                chain_id=chain_id,
                original_chain=input_chain,
                status="rejected",
                quality_score=0.0,
                llm_judgment=None,
                issues=[reason]
            )

        # 获取 PR 信息
        pr_data = self.fetcher.fetch_pr_batch(
            input_chain,
            max_workers=self.max_workers,
            fetch_files=False
        )
        prs = [pr_data[pr_id] for pr_id in input_chain if pr_data.get(pr_id) is not None]

        if len(prs) != len(input_chain):
            return FilterResult(
                chain_id=chain_id,
                original_chain=input_chain,
                status="rejected",
                quality_score=0.0,
                llm_judgment=None,
                issues=["failed_to_fetch_prs"]
            )

        # 按时间顺序调整 PR 链
        prs = sorted(prs, key=lambda pr: pr.created_at)
        ordered_chain = [pr.pr_id for pr in prs]

        # 检查是否所有 PR 已合并
        if not all(pr.merged_at for pr in prs):
            return FilterResult(
                chain_id=chain_id,
                original_chain=input_chain,
                status="rejected",
                quality_score=0.0,
                llm_judgment=None,
                issues=["contains_unmerged_pr"]
            )

        # LLM 判断
        try:
            llm_result = self.llm_judge.judge_chain(prs, prs[0].repo)
        except Exception as e:
            return FilterResult(
                chain_id=chain_id,
                original_chain=input_chain,
                status="rejected",
                quality_score=0.0,
                llm_judgment=None,
                issues=[f"llm_error: {str(e)}"]
            )

        # 文件重叠分析（如果需要）
        file_overlap = None
        if llm_result.overall_score >= 5.0:
            file_overlap = self._analyze_file_overlap(ordered_chain)

        # 最终决策
        status = self._make_decision(llm_result, file_overlap)

        return FilterResult(
            chain_id=chain_id,
            original_chain=input_chain,
            status=status,
            quality_score=llm_result.overall_score,
            llm_judgment=llm_result,
            issues=llm_result.issues,
            file_overlap_rate=file_overlap
        )

    def _pre_filter(self, chain: List[str]) -> Tuple[bool, str]:
        """预筛选"""
        min_len = self.config['filtering']['min_chain_length']
        max_len = self.config['filtering']['max_chain_length']

        if len(chain) < min_len:
            return False, "chain_too_short"
        if len(chain) > max_len:
            return False, "chain_too_long"

        # 检查同一仓库
        repos = set(pr.split('#')[0] for pr in chain)
        if len(repos) > 1:
            return False, "multiple_repos"

        return True, ""

    def _analyze_file_overlap(self, chain: List[str]) -> float:
        """分析文件重叠率"""
        # 获取文件列表
        pr_data_with_files = self.fetcher.fetch_pr_batch(
            chain,
            max_workers=self.max_workers,
            fetch_files=True
        )

        total_overlap = 0
        comparisons = 0

        for i in range(len(chain) - 1):
            pr1 = pr_data_with_files.get(chain[i])
            pr2 = pr_data_with_files.get(chain[i + 1])

            if pr1 and pr2 and pr1.files and pr2.files:
                files1 = set(pr1.files)
                files2 = set(pr2.files)
                overlap = len(files1 & files2) / len(files1 | files2) if files1 | files2 else 0
                total_overlap += overlap
                comparisons += 1

        return total_overlap / comparisons if comparisons > 0 else 0.0

    def _make_decision(self, llm_result: LLMJudgment, file_overlap: Optional[float] = None) -> str:
        """最终决策"""
        threshold = self.config['filtering']['score_threshold']
        confidence_threshold = self.config['filtering']['confidence_threshold']

        if llm_result.overall_score >= threshold and llm_result.confidence >= confidence_threshold:
            return "approved"

        # 边界情况：检查文件重叠
        if file_overlap and file_overlap >= 0.3 and llm_result.overall_score >= 6.0:
            return "approved"

        return "rejected"
