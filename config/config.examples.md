# Configuration Examples

## Example 1: Using OpenAI GPT-4

```yaml
llm:
  provider: openai
  api_key: ${OPENAI_API_KEY}
  model: gpt-4
  base_url: null
  max_tokens: 2048
```

Set environment variable:
```bash
export OPENAI_API_KEY="sk-..."
```

## Example 2: Using Claude (Anthropic)

```yaml
llm:
  provider: anthropic
  api_key: ${ANTHROPIC_API_KEY}
  model: claude-3-5-sonnet-20241022
  base_url: null
  max_tokens: 2048
```

Set environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Example 3: Using DeepSeek (OpenAI-compatible)

```yaml
llm:
  provider: openai
  api_key: ${DEEPSEEK_API_KEY}
  model: deepseek-chat
  base_url: https://api.deepseek.com
  max_tokens: 2048
```

Set environment variable:
```bash
export DEEPSEEK_API_KEY="sk-..."
```

## Example 4: Using Local LLM (OpenAI-compatible)

```yaml
llm:
  provider: openai
  api_key: dummy  # some local servers don't need a key
  model: llama-3-70b
  base_url: http://localhost:8000/v1
  max_tokens: 2048
```

## Full Configuration Template

```yaml
github:
  tokens:
    - ${GITHUB_TOKEN}
    - ${GITHUB_TOKEN_BACKUP}
  rate_limit_delay: 0.5
  max_workers: 20

llm:
  provider: openai  # anthropic or openai
  api_key: ${OPENAI_API_KEY}
  model: gpt-4
  base_url: null
  max_tokens: 2048

filtering:
  score_threshold: 7.0
  confidence_threshold: 0.7
  min_chain_length: 2
  max_chain_length: 10

cache:
  dir: data/cache
```
