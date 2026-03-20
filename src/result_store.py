"""Result persistence and resume helpers."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from .chain_identity import build_chain_id, is_legacy_chain_id


@dataclass
class ResultStoreSnapshot:
    """Summary of an existing output file."""
    completed_ids: set[str]
    approved: int
    rejected: int
    invalid_lines: int
    duplicate_ids: int


def serialize_filter_result(result) -> dict:
    """Serialize a FilterResult for JSONL output."""
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


def read_result_chain_id(item: dict) -> Optional[str]:
    """Read a stable chain id from a result item, with legacy fallback."""
    chain = item.get('original_chain')
    if isinstance(chain, list) and chain:
        try:
            return build_chain_id(chain)
        except Exception:
            pass
    chain_id = item.get('chain_id')
    if isinstance(chain_id, str) and chain_id and not is_legacy_chain_id(chain_id):
        return chain_id
    return None


def load_valid_result_items(input_path: str) -> tuple[list[dict], int]:
    """Load valid result items from JSONL, normalizing chain_id."""
    items: list[dict] = []
    invalid_lines = 0
    path = Path(input_path)

    if not path.exists():
        return items, invalid_lines

    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue

            chain_id = read_result_chain_id(item)
            if not chain_id:
                invalid_lines += 1
                continue

            item['chain_id'] = chain_id
            items.append(item)

    return items, invalid_lines


def load_result_snapshot(output_path: str) -> ResultStoreSnapshot:
    """Load existing results for resume and reporting."""
    completed_status: Dict[str, str] = {}
    duplicate_ids = 0
    items, invalid_lines = load_valid_result_items(output_path)

    for item in items:
        chain_id = item['chain_id']
        if chain_id in completed_status:
            duplicate_ids += 1
        completed_status[chain_id] = item.get('status')

    approved = sum(1 for status in completed_status.values() if status == 'approved')
    rejected = sum(1 for status in completed_status.values() if status != 'approved')
    return ResultStoreSnapshot(set(completed_status.keys()), approved, rejected, invalid_lines, duplicate_ids)


def load_compacted_results(input_path: str) -> tuple[dict[str, dict], int]:
    """Load and deduplicate an output file by chain_id, keeping the latest entry."""
    compacted: dict[str, dict] = {}
    items, invalid_lines = load_valid_result_items(input_path)

    for item in items:
        chain_id = item['chain_id']
        if chain_id in compacted:
            compacted.pop(chain_id)
        compacted[chain_id] = item

    return compacted, invalid_lines


def write_results_jsonl(output_path: str, items: Iterable[dict]):
    """Write JSONL items to disk."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
