# 使用示例

## 快速开始

### 1. 设置环境变量

```bash
export GITHUB_TOKEN="your_github_access_token"
export ANTHROPIC_API_KEY="your_anthropic_api_key"
```

### 2. 运行筛选（测试 5 条链）

```bash
cd ~/Repos/pr-chain-curator

python cli.py filter \
  --input data/input/PR-list.jsonl \
  --output data/output/filtered.jsonl \
  --max-chains 5
```

### 3. 查看统计

```bash
python cli.py stats --input data/output/filtered.jsonl
```

## 完整运行（所有 149 条链）

```bash
python cli.py filter \
  --input data/input/PR-list.jsonl \
  --output data/output/filtered_all.jsonl
```

预计耗时：5-10 分钟
预计成本：~$0.30

## 输出说明

### 筛选结果文件格式

每行一个 JSON 对象：

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
    "scores": {
      "topic_consistency": 9,
      "logical_relevance": 8,
      "temporal_reasonableness": 9,
      "author_consistency": 8
    },
    "reasoning": "这些 PR 围绕 sparse matrix 功能的渐进式改进",
    "evolution_pattern": "incremental_enhancement",
    "function_types": ["ENH"],
    "issues": []
  },
  "issues": []
}
```

### 字段说明

- `status`: "approved" 或 "rejected"
- `quality_score`: LLM 评分 (0-10)
- `file_overlap_rate`: 文件重叠率 (0-1)
- `evolution_pattern`: 演化模式
  - `incremental_enhancement`: 渐进式增强
  - `iterative_bugfix`: 迭代修复
  - `long_term_refactoring`: 长期重构
  - `collaborative_development`: 协作开发
- `function_types`: 功能类型列表 (ENH/BUG/MAINT/DOC/TST/PERF)

## 提取通过的链

```bash
# 提取所有通过的链
cat data/output/filtered.jsonl | jq 'select(.status == "approved")' > data/output/approved_only.jsonl

# 统计通过率
total=$(cat data/output/filtered.jsonl | wc -l)
approved=$(cat data/output/filtered.jsonl | jq 'select(.status == "approved")' | wc -l)
echo "通过率: $approved / $total"
```

## 调整筛选阈值

编辑 `config/config.yaml`:

```yaml
filtering:
  score_threshold: 7.0  # 降低到 6.0 会更宽松
  confidence_threshold: 0.7  # LLM 置信度阈值
```

## 缓存管理

```bash
# 查看缓存大小
du -sh data/cache

# 清空缓存（重新获取所有数据）
rm -rf data/cache/*
```

## 故障排查

### GitHub API 速率限制

如果遇到速率限制，增加延迟：

```yaml
github:
  rate_limit_delay: 1.0  # 从 0.5 增加到 1.0
```

### LLM 解析错误

如果 LLM 返回格式错误，检查 `llm_judge.py` 的 `_parse_response` 方法。

### 内存不足

减少并发数：

```yaml
github:
  max_workers: 10  # 从 20 减少到 10
```
