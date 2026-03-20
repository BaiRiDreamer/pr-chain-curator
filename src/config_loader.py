"""Configuration loading helpers."""
import os
import re

import yaml

ENV_VAR_PATTERN = re.compile(r'^\$\{([A-Z0-9_]+)\}$')


def resolve_env_placeholders(value):
    """Recursively resolve ${ENV_VAR} placeholders in config values."""
    if isinstance(value, dict):
        return {key: resolve_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_env_placeholders(item) for item in value]
    if isinstance(value, str):
        match = ENV_VAR_PATTERN.fullmatch(value.strip())
        if match:
            return os.getenv(match.group(1), value)
    return value


def load_config(config_path: str) -> dict:
    """Load config and hydrate environment-backed credentials."""
    with open(config_path) as f:
        config = resolve_env_placeholders(yaml.safe_load(f))

    github_cfg = config.setdefault('github', {})
    tokens = github_cfg.get('tokens') or []
    if isinstance(tokens, str):
        tokens = [tokens]
    tokens = [token for token in tokens if token and not token.startswith('${')]
    fallback_token = os.getenv('GITHUB_TOKEN', github_cfg.get('token'))
    if fallback_token:
        tokens.append(fallback_token)
    github_cfg['tokens'] = list(dict.fromkeys(tokens))

    llm_cfg = config['llm']
    if llm_cfg['provider'] == 'anthropic':
        llm_cfg['api_key'] = os.getenv('ANTHROPIC_API_KEY', llm_cfg['api_key'])
    elif llm_cfg['provider'] == 'azure':
        llm_cfg['api_key'] = os.getenv(
            'AZURE_OPENAI_API_KEY',
            os.getenv('OPENAI_API_KEY', llm_cfg['api_key'])
        )
    else:
        llm_cfg['api_key'] = os.getenv('OPENAI_API_KEY', llm_cfg['api_key'])

    return config
