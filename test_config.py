#!/usr/bin/env python3
"""测试 LLM 配置"""
import yaml
import os

def test_config():
    """测试配置加载"""
    print("Testing configuration...")

    # 加载配置
    with open('config/config.yaml') as f:
        config = yaml.safe_load(f)

    print(f"✓ Config loaded")
    print(f"  LLM Provider: {config['llm']['provider']}")
    print(f"  LLM Model: {config['llm']['model']}")
    print(f"  Base URL: {config['llm'].get('base_url', 'None')}")

    # 测试环境变量
    if config['llm']['provider'] == 'openai':
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            print(f"✓ OPENAI_API_KEY found: {api_key[:10]}...")
        else:
            print("⚠ OPENAI_API_KEY not set")
    else:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if api_key:
            print(f"✓ ANTHROPIC_API_KEY found: {api_key[:10]}...")
        else:
            print("⚠ ANTHROPIC_API_KEY not set")

    github_token = os.getenv('GITHUB_TOKEN')
    if github_token:
        print(f"✓ GITHUB_TOKEN found: {github_token[:10]}...")
    else:
        print("⚠ GITHUB_TOKEN not set")

    # 测试导入
    try:
        from src.llm_judge import LLMJudge
        print("✓ LLMJudge import successful")

        if config['llm']['provider'] == 'openai':
            import openai
            print("✓ openai library available")
        else:
            import anthropic
            print("✓ anthropic library available")

    except ImportError as e:
        print(f"✗ Import error: {e}")

    print("\n✅ Configuration test complete!")
    print("\nTo run filtering:")
    print("  python cli.py filter --input data/input/PR-list.jsonl --output data/output/filtered.jsonl --max-chains 2")

if __name__ == '__main__':
    test_config()
