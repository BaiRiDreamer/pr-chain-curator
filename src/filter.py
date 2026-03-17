"""筛选器模块"""
import json
from typing import List, Dict, Tuple
from .models import PRChain, PullRequest, FilterResult, LLMJudgment
from .fetcher import GitHubFetcher
from .llm_judge import LLMJudge

class ChainFilter:
    """PR 链筛选器"""

    def __init__(self, fetcher: GitHubFetcher, llm_judge: LLMJudge, config: Dict):
        self.fetcher = fetcher
        self.llm_judge = llm_judge
        self.config = config

    def filter_chains(self, chains: List[List[str]]) -> List[FilterResult]:
        """筛选 PR 链"""
        results = []

        for idx, chain in enumerate(chains):
            chain_id = f"chain_{idx:04d}"
            print(f"Processing {chain_id}: {chain[0]}...")

            # 预筛选
            passed, reason = self._pre_filter(chain)
            if not passed:
                results.append(FilterResult(
                    chain_id=chain_id,
                    original_chain=chain,
                    status="rejected",
                    quality_score=0.0,
                    llm_judgment=None,
                    issues=[reason]
                ))
                continue

            # 获取 PR 信息
            pr_data = self.fetcher.fetch_pr_batch(chain, fetch_files=False)
            prs = [pr_data[pr_id] for pr_id in chain if pr_id in pr_data]

            if len(prs) != len(chain):
                results.append(FilterResult(
                    chain_id=chain_id,
                    original_chain=chain,
                    status="rejected",
                    quality_score=0.0,
                    llm_judgment=None,
                    issues=["failed_to_fetch_prs"]
                ))
                continue

            # 检查是否所有 PR 已合并
            if not all(pr.merged_at for pr in prs):
                results.append(FilterResult(
                    chain_id=chain_id,
                    original_chain=chain,
                    status="rejected",
                    quality_score=0.0,
                    llm_judgment=None,
                    issues=["contains_unmerged_pr"]
                ))
                continue

            # LLM 判断
            try:
                llm_result = self.llm_judge.judge_chain(prs, prs[0].repo)
            except Exception as e:
                print(f"LLM error: {e}")
                results.append(FilterResult(
                    chain_id=chain_id,
                    original_chain=chain,
                    status="rejected",
                    quality_score=0.0,
                    llm_judgment=None,
                    issues=[f"llm_error: {str(e)}"]
                ))
                continue

            # 文件重叠分析（如果需要）
            file_overlap = None
            if llm_result.overall_score >= 5.0:
                file_overlap = self._analyze_file_overlap(chain, prs)

            # 最终决策
            status = self._make_decision(llm_result, file_overlap)

            results.append(FilterResult(
                chain_id=chain_id,
                original_chain=chain,
                status=status,
                quality_score=llm_result.overall_score,
                llm_judgment=llm_result,
                issues=llm_result.issues,
                file_overlap_rate=file_overlap
            ))

        return results

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

    def _analyze_file_overlap(self, chain: List[str], prs: List[PullRequest]) -> float:
        """分析文件重叠率"""
        # 获取文件列表
        pr_data_with_files = self.fetcher.fetch_pr_batch(chain, fetch_files=True)

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

    def _make_decision(self, llm_result: LLMJudgment, file_overlap: float = None) -> str:
        """最终决策"""
        threshold = self.config['filtering']['score_threshold']
        confidence_threshold = self.config['filtering']['confidence_threshold']

        if llm_result.overall_score >= threshold and llm_result.confidence >= confidence_threshold:
            return "approved"

        # 边界情况：检查文件重叠
        if file_overlap and file_overlap >= 0.3 and llm_result.overall_score >= 6.0:
            return "approved"

        return "rejected"
