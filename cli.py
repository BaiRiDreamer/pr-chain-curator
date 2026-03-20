"""命令行入口"""
import json
import os
import click
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.chain_identity import build_chain_id
from src.config_loader import load_config
from src.fetcher import GitHubFetcher
from src.llm_judge import LLMJudge
from src.filter import ChainFilter
from src.models import FilterResult
from src.result_store import (
    load_compacted_results,
    load_result_snapshot,
    serialize_filter_result,
    write_results_jsonl,
)

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
    if not cfg['github'].get('tokens'):
        raise click.ClickException("No GitHub tokens configured. Set github.tokens or GITHUB_TOKEN.")

    # 初始化组件
    fetcher = GitHubFetcher(
        tokens=cfg['github']['tokens'],
        cache_dir=cfg['cache']['dir'],
        rate_limit_delay=cfg['github']['rate_limit_delay'],
        request_timeout=cfg['github'].get('request_timeout', 30.0),
        max_retries=cfg['github'].get('max_retries', 3),
        retry_backoff=cfg['github'].get('retry_backoff', 2.0),
        max_retry_wait=cfg['github'].get('max_retry_wait', 60.0)
    )

    llm_judge = LLMJudge(
        provider=cfg['llm']['provider'],
        api_key=cfg['llm']['api_key'],
        model=cfg['llm']['model'],
        base_url=cfg['llm'].get('base_url'),
        max_tokens=cfg['llm']['max_tokens'],
        api_version=cfg['llm'].get('api_version'),
        azure_endpoint=cfg['llm'].get('azure_endpoint'),
        default_headers=cfg['llm'].get('default_headers'),
        request_timeout=cfg['llm'].get('request_timeout', 60.0),
        max_retries=cfg['llm'].get('max_retries', 3),
        retry_backoff=cfg['llm'].get('retry_backoff', 2.0),
        max_retry_wait=cfg['llm'].get('max_retry_wait', 60.0)
    )

    chain_filter = ChainFilter(fetcher, llm_judge, cfg)

    # 加载链
    with open(input) as f:
        data = json.load(f)
    chains = data['chains']

    if max_chains:
        chains = chains[:max_chains]

    snapshot = load_result_snapshot(output)
    pending = []
    seen_chain_ids = set(snapshot.completed_ids)
    duplicate_inputs = 0
    for idx, chain in enumerate(chains, start=1):
        chain_id = build_chain_id(chain)
        if chain_id in seen_chain_ids:
            if chain_id not in snapshot.completed_ids:
                duplicate_inputs += 1
            continue
        seen_chain_ids.add(chain_id)
        pending.append((idx, chain_id, chain))

    total = len(chains)
    chain_workers = chain_workers or cfg['filtering'].get('chain_workers', 1)
    chain_workers = max(1, min(chain_workers, len(pending))) if pending else 1

    click.echo(
        f"Processing {total} chains with {chain_workers} chain worker(s); "
        f"{len(snapshot.completed_ids)} already completed, {len(pending)} pending."
    )
    if duplicate_inputs > 0:
        click.echo(f"Skipped {duplicate_inputs} duplicate chain(s) already present in the current input.")
    if snapshot.invalid_lines > 0:
        click.echo(
            f"Warning: ignored {snapshot.invalid_lines} invalid line(s) in existing output during resume."
        )
    if snapshot.duplicate_ids > 0:
        click.echo(
            f"Warning: existing output contains {snapshot.duplicate_ids} duplicate chain id line(s). "
            f"Run `compact-output` to clean it."
        )

    if not pending:
        click.echo(f"\nResults: {snapshot.approved} approved, {snapshot.rejected} rejected")
        click.echo(f"Results already complete in {output}")
        return

    approved = snapshot.approved
    rejected = snapshot.rejected
    os.makedirs(os.path.dirname(output) or '.', exist_ok=True)
    file_mode = 'a' if snapshot.completed_ids else 'w'
    with open(output, file_mode, encoding='utf-8', buffering=1) as f:
        with ThreadPoolExecutor(max_workers=chain_workers) as executor:
            futures = {}
            for idx, chain_id, chain in pending:
                futures[executor.submit(chain_filter.filter_chain, chain_id, chain)] = (
                    idx, chain_id, chain
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


@cli.command('compact-output')
@click.option('--input', 'input_path', required=True, help='输入结果文件（JSONL）')
@click.option('--output', 'output_path', required=True, help='输出去重后的结果文件（JSONL）')
def compact_output(input_path, output_path):
    """按 chain_id 去重结果文件，保留每个 chain_id 的最后一条记录"""
    compacted, invalid_lines = load_compacted_results(input_path)
    write_results_jsonl(output_path, compacted.values())
    click.echo(
        f"Compacted {len(compacted)} unique chain(s) to {output_path}."
    )
    if invalid_lines > 0:
        click.echo(f"Ignored {invalid_lines} invalid line(s) while compacting.")

@cli.command()
@click.option('--input', required=True, help='筛选结果文件')
def stats(input):
    """显示统计信息"""
    compacted, invalid_lines = load_compacted_results(input)
    results = list(compacted.values())

    if not results:
        click.echo("No valid data found in input file.")
        if invalid_lines > 0:
            click.echo(f"Ignored {invalid_lines} invalid line(s).")
        return

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

    if invalid_lines > 0:
        click.echo(f"\nIgnored invalid lines: {invalid_lines}")

if __name__ == '__main__':
    cli()
