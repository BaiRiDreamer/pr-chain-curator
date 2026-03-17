# PR Chain Curator

自动化筛选和标注 GitHub PR 演化链，基于 LLM 进行语义分析。

## 功能特性

- ✅ 基于 LLM 的语义分析和质量评估
- ✅ 多线程并发处理 GitHub API
- ✅ 文件系统缓存机制
- ✅ 文件重叠分析
- ✅ 多维度标注（演化模式、功能类型）

## 安装

```bash
cd ~/Repos/pr-chain-curator
pip install -r requirements.txt
```

## 配置

设置环境变量：

```bash
export GITHUB_TOKEN="your_github_token"
export ANTHROPIC_API_KEY="your_anthropic_key"
```

或编辑 `config/config.yaml`。

## 使用

### 筛选 PR 链

```bash
python cli.py filter \
  --input data/input/PR-list.jsonl \
  --output data/output/filtered.jsonl \
  --max-chains 10
```

### 查看统计

```bash
python cli.py stats --input data/output/filtered.jsonl
```

## 输出格式

```json
{
  "chain_id": "chain_0001",
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

## 项目结构

```
pr-chain-curator/
├── cli.py              # 命令行入口
├── config/             # 配置文件
├── src/
│   ├── models.py       # 数据模型
│   ├── cache.py        # 缓存机制
│   ├── fetcher.py      # GitHub API
│   ├── llm_judge.py    # LLM 判断
│   └── filter.py       # 筛选逻辑
└── data/
    ├── input/          # 输入数据
    ├── output/         # 筛选结果
    └── cache/          # API 缓存
```

## License

MIT
