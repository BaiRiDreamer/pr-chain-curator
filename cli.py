"""命令行入口"""
import json
import os
import yaml
import click
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.fetcher import GitHubFetcher
from src.llm_judge import LLMJudge
from src.filter import ChainFilter
from src.models import FilterResult

def load_config(config_path: str) -> dict:
    """加载配置"""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 替换环境变量
    config['github']['token'] = os.getenv('GITHUB_TOKEN', config['github']['token'])

    # LLM 配置
    if config['llm']['provider'] == 'anthropic':
        config['llm']['api_key'] = os.getenv('ANTHROPIC_API_KEY', config['llm']['api_key'])
    else:  # openai
        config['llm']['api_key'] = os.getenv('OPENAI_API_KEY', config['llm']['api_key'])

    return config

def serialize_filter_result(result) -> dict:
    """序列化筛选结果，用于 JSONL 流式写出"""
    return {
        'chain_id': result.chain_id,
        'original_chain': result.original_chain,
        'status': result.status,
        'quality_score': result.quality_score,
        'file_overlap_rate': result.file_overlap_rate,
        'llm_judgment': {
            'is_valid_chain': result.llm_judgment.is_valid_chain,
            'confidence': result.llm_judgment.confidence,
            'overall_score': result.llm_judgment.overall_score,
            'scores': result.llm_judgment.scores,
            'reasoning': result.llm_judgment.reasoning,
            'evolution_pattern': result.llm_judgment.evolution_pattern,
            'function_types': result.llm_judgment.function_types,
            'issues': result.llm_judgment.issues
        } if result.llm_judgment else None,
        'issues': result.issues
    }

@click.group()
def cli():
    """PR Chain Curator - 筛选和标注 PR 链"""
    pass

@cli.command()
@click.option('--input', required=True, help='输入文件路径')
@click.option('--output', required=True, help='输出文件路径')
@click.option('--config', default='config/config.yaml', help='配置文件')
@click.option('--max-chains', type=int, help='限制处理数量')
@click.option('--chain-workers', type=int, help='链间并发数，默认读取 filtering.chain_workers')
def filter(input, output, config, max_chains, chain_workers):
    """筛选 PR 链"""
    # 加载配置
    cfg = load_config(config)

    # 初始化组件
    fetcher = GitHubFetcher(
        token=cfg['github']['token'],
        cache_dir=cfg['cache']['dir'],
        rate_limit_delay=cfg['github']['rate_limit_delay']
    )

    llm_judge = LLMJudge(
        provider=cfg['llm']['provider'],
        api_key=cfg['llm']['api_key'],
        model=cfg['llm']['model'],
        base_url=cfg['llm'].get('base_url'),
        max_tokens=cfg['llm']['max_tokens'],
        api_version=cfg['llm'].get('api_version'),
        azure_endpoint=cfg['llm'].get('azure_endpoint'),
        default_headers=cfg['llm'].get('default_headers')
    )

    chain_filter = ChainFilter(fetcher, llm_judge, cfg)

    # 加载链
    with open(input) as f:
        data = json.load(f)
    chains = data['chains']

    if max_chains:
        chains = chains[:max_chains]

    total = len(chains)
    chain_workers = chain_workers or cfg['filtering'].get('chain_workers', 1)
    chain_workers = max(1, min(chain_workers, total)) if total > 0 else 1

    click.echo(f"Processing {total} chains with {chain_workers} chain worker(s)...")

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    approved = 0
    rejected = 0

    with open(output, 'w', encoding='utf-8', buffering=1) as f:
        with ThreadPoolExecutor(max_workers=chain_workers) as executor:
            futures = {}
            for idx, chain in enumerate(chains):
                chain_id = f"chain_{idx:04d}"
                futures[executor.submit(chain_filter.filter_chain, chain_id, chain)] = (
                    idx + 1, chain_id, chain
                )

            for future in as_completed(futures):
                idx, chain_id, chain = futures[future]
                click.echo(f"\n[{idx}/{total}] Completed {chain_id}: {chain[0]}")

                try:
                    result = future.result()
                except Exception as exc:
                    result = FilterResult(
                        chain_id=chain_id,
                        original_chain=chain,
                        status='rejected',
                        quality_score=0.0,
                        llm_judgment=None,
                        issues=[f"unexpected_error: {exc}"]
                    )
                item = serialize_filter_result(result)
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())

                if result.status == 'approved':
                    approved += 1
                else:
                    rejected += 1

                overlap_text = (
                    f", overlap={result.file_overlap_rate:.2f}"
                    if result.file_overlap_rate is not None else ""
                )
                click.echo(
                    f"[{idx}/{total}] {result.chain_id} -> {result.status} "
                    f"(score={result.quality_score:.2f}{overlap_text}, "
                    f"approved={approved}, rejected={rejected})"
                )

    click.echo(f"\nResults: {approved} approved, {rejected} rejected")

    click.echo(f"Results saved to {output}")

@cli.command()
@click.option('--input', required=True, help='筛选结果文件')
def stats(input):
    """显示统计信息"""
    results = []
    with open(input) as f:
        for line in f:
            results.append(json.loads(line))

    total = len(results)
    approved = sum(1 for r in results if r['status'] == 'approved')
    rejected = total - approved

    click.echo(f"\n{'='*50}")
    click.echo(f"Total chains: {total}")
    click.echo(f"Approved: {approved} ({approved/total*100:.1f}%)")
    click.echo(f"Rejected: {rejected} ({rejected/total*100:.1f}%)")

    # 分数分布
    scores = [r['quality_score'] for r in results if r['quality_score']]
    if scores:
        click.echo(f"\nScore distribution:")
        click.echo(f"  Mean: {sum(scores)/len(scores):.2f}")
        click.echo(f"  Min: {min(scores):.2f}")
        click.echo(f"  Max: {max(scores):.2f}")

    # 演化模式分布
    patterns = {}
    for r in results:
        if r.get('llm_judgment') and r['llm_judgment']:
            pattern = r['llm_judgment']['evolution_pattern']
            patterns[pattern] = patterns.get(pattern, 0) + 1

    if patterns:
        click.echo(f"\nEvolution patterns:")
        for pattern, count in sorted(patterns.items(), key=lambda x: -x[1]):
            click.echo(f"  {pattern}: {count}")

if __name__ == '__main__':
    cli()
