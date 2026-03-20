# PR Chain Curator

自动化筛选和标注 GitHub PR 演化链，基于 LLM 进行语义分析。

## 功能特性

- ✅ 基于 LLM 的语义分析和质量评估（支持 OpenAI 和 Anthropic）
- ✅ 多线程并发处理 GitHub API
- ✅ 文件系统缓存机制
- ✅ 文件重叠分析
- ✅ 多维度标注（演化模式、功能类型）
- ✅ 支持 OpenAI 兼容的 API（DeepSeek、本地模型等）

## 安装

```bash
cd ~/Repos/pr-chain-curator
python3 -m pip install -r requirements.txt
```

## 配置

### 使用 OpenAI (推荐)

```bash
export GITHUB_TOKEN="your_github_token"
export OPENAI_API_KEY="your_openai_key"
```

编辑 `config/config.yaml`:
```yaml
llm:
  provider: openai
  model: gpt-4
```

### 使用 Anthropic Claude

```bash
export GITHUB_TOKEN="your_github_token"
export ANTHROPIC_API_KEY="your_anthropic_key"
```

编辑 `config/config.yaml`:
```yaml
llm:
  provider: anthropic
  model: claude-3-5-sonnet-20241022
```

### 使用 OpenAI 兼容 API (DeepSeek 等)

```bash
export GITHUB_TOKEN="your_github_token"
export DEEPSEEK_API_KEY="your_deepseek_key"
```

编辑 `config/config.yaml`:
```yaml
llm:
  provider: openai
  api_key: ${DEEPSEEK_API_KEY}
  model: deepseek-chat
  base_url: https://api.deepseek.com
```

GitHub token 也可以配置成池：
```yaml
github:
  tokens:
    - ${GITHUB_TOKEN}
    - ${GITHUB_TOKEN_BACKUP}
```

更多配置示例见 `config/config.examples.md`。

## 使用

### 筛选 PR 链

```bash
python3 cli.py filter \
  --input data/input/PR-list.jsonl \
  --output data/output/filtered.jsonl \
  --max-chains 10
```

### 查看统计

```bash
python3 cli.py stats --input data/output/filtered.jsonl
```

## 输出格式

```json
{
  "chain_id": "scipy/scipy|229|243|6f7c4f2a",
  "original_chain": ["scipy/scipy#229", "scipy/scipy#243"],
  "status": "approved",
  "quality_score": 8.5,
  "file_overlap_rate": 0.65,
  "llm_judgment": {
    "is_valid_chain": true,
    "confidence": 0.9,
    "overall_score": 8.5,
    "reasoning": "...",
    "evolution_pattern": "incremental_enhancement",
    "function_types": ["ENH"]
  }
}
```

## 筛选标准

- **预筛选**: 链长度 2-10，同一仓库
- **LLM 评分**: overall_score >= 7.0
- **文件重叠**: 相邻 PR 文件重叠率 >= 30%（边界情况）

## 结果维护

如果历史 output 中已有重复结果，可以先压缩：

```bash
python3 cli.py compact-output \
  --input data/output/filtered.jsonl \
  --output data/output/filtered.compacted.jsonl
```

## 项目结构

```
pr-chain-curator/
├── cli.py              # 命令行入口
├── config/             # 配置文件
├── src/
│   ├── models.py            # 数据模型
│   ├── cache.py             # 缓存机制
│   ├── chain_identity.py    # 稳定 chain_id 生成
│   ├── config_loader.py     # 配置加载
│   ├── github_token_pool.py # GitHub token 池
│   ├── result_store.py      # 结果读写/续跑/去重
│   ├── fetcher.py           # GitHub API
│   ├── llm_judge.py         # LLM 判断
│   └── filter.py            # 筛选逻辑
└── data/
    ├── input/          # 输入数据
    ├── output/         # 筛选结果
    └── cache/          # API 缓存
```

## License

MIT
