"""命令行入口"""
import json
import os
import yaml
import click
from pathlib import Path
from src.fetcher import GitHubFetcher
from src.llm_judge import LLMJudge
from src.filter import ChainFilter

def load_config(config_path: str) -> dict:
    """加载配置"""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 替换环境变量
    config['github']['token'] = os.getenv('GITHUB_TOKEN', config['github']['token'])
    config['anthropic']['api_key'] = os.getenv('ANTHROPIC_API_KEY', config['anthropic']['api_key'])
    return config

@click.group()
def cli():
    """PR Chain Curator - 筛选和标注 PR 链"""
    pass

@cli.command()
@click.option('--input', required=True, help='输入文件路径')
@click.option('--output', required=True, help='输出文件路径')
@click.option('--config', default='config/config.yaml', help='配置文件')
@click.option('--max-chains', type=int, help='限制处理数量')
def filter(input, output, config, max_chains):
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
        api_key=cfg['anthropic']['api_key'],
        model=cfg['anthropic']['model'],
        max_tokens=cfg['anthropic']['max_tokens']
    )

    chain_filter = ChainFilter(fetcher, llm_judge, cfg)

    # 加载链
    with open(input) as f:
        data = json.load(f)
    chains = data['chains']

    if max_chains:
        chains = chains[:max_chains]

    click.echo(f"Processing {len(chains)} chains...")

    # 筛选
    results = chain_filter.filter_chains(chains)

    # 统计
    approved = sum(1 for r in results if r.status == 'approved')
    rejected = sum(1 for r in results if r.status == 'rejected')

    click.echo(f"\nResults: {approved} approved, {rejected} rejected")

    # 保存结果
    output_data = []
    for result in results:
        output_data.append({
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
        })

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w') as f:
        for item in output_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

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
