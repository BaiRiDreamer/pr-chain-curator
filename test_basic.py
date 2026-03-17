#!/usr/bin/env python3
"""测试脚本 - 不使用真实 API"""
import json
from datetime import datetime

# 模拟测试
def test_basic_flow():
    """测试基本流程"""
    print("Testing PR Chain Curator...")

    # 1. 测试数据加载
    with open('data/input/PR-list.jsonl') as f:
        data = json.load(f)

    chains = data['chains']
    print(f"✓ Loaded {len(chains)} chains")

    # 2. 测试预筛选
    from src.filter import ChainFilter

    valid_chains = []
    for chain in chains[:5]:
        # 检查长度
        if 2 <= len(chain) <= 10:
            # 检查同一仓库
            repos = set(pr.split('#')[0] for pr in chain)
            if len(repos) == 1:
                valid_chains.append(chain)

    print(f"✓ Pre-filter: {len(valid_chains)}/5 chains passed")

    # 3. 测试缓存
    from src.cache import FileCache
    cache = FileCache('data/cache')
    cache.set('test_key', {'data': 'test'})
    result = cache.get('test_key')
    assert result['data'] == 'test'
    print("✓ Cache working")

    # 4. 测试 PR ID 解析
    pr_id = "scipy/scipy#229"
    repo, number = pr_id.split('#')
    assert repo == "scipy/scipy"
    assert int(number) == 229
    print("✓ PR ID parsing working")

    print("\n✅ All basic tests passed!")
    print("\nTo run full filtering (requires API keys):")
    print("  export GITHUB_TOKEN='your_token'")
    print("  export ANTHROPIC_API_KEY='your_key'")
    print("  python cli.py filter --input data/input/PR-list.jsonl --output data/output/filtered.jsonl --max-chains 5")

if __name__ == '__main__':
    test_basic_flow()
