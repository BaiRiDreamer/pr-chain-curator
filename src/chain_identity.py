"""PR chain identity helpers."""
from hashlib import sha1
from typing import List, Sequence, Tuple


def normalize_pr_id(pr_id: str) -> Tuple[str, int]:
    """Normalize a PR id into (repo, number)."""
    repo, number = pr_id.strip().split('#', 1)
    return repo.strip().lower(), int(number)


def canonicalize_chain(chain: Sequence[str]) -> List[Tuple[str, int]]:
    """Canonicalize a chain so the same chain yields the same id regardless of input order."""
    normalized = [normalize_pr_id(pr_id) for pr_id in chain]
    repos = {repo for repo, _ in normalized}
    if len(repos) == 1:
        repo = normalized[0][0]
        numbers = sorted(number for _, number in normalized)
        return [(repo, number) for number in numbers]
    return sorted(normalized, key=lambda item: (item[0], item[1]))


def build_chain_id(chain: Sequence[str]) -> str:
    """Build a stable, readable chain id from the PR chain content."""
    canonical = canonicalize_chain(chain)
    if not canonical:
        return "empty-chain|da39a3ee"

    repos = {repo for repo, _ in canonical}
    digest_source = "|".join(f"{repo}#{number}" for repo, number in canonical)
    digest = sha1(digest_source.encode("utf-8")).hexdigest()[:8]

    if len(repos) == 1:
        repo = canonical[0][0]
        numbers = "|".join(str(number) for _, number in canonical)
        return f"{repo}|{numbers}|{digest}"

    parts = "|".join(f"{repo}#{number}" for repo, number in canonical)
    return f"multi-repo|{parts}|{digest}"


def is_legacy_chain_id(value: str) -> bool:
    """Return True when the chain id looks like the old positional format."""
    if not isinstance(value, str):
        return False
    return value.startswith("chain_")
