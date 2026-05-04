"""
MCP prompt definitions for the query client.
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_prompts() -> Dict[str, Any]:
    config_path = Path(__file__).parent / "config_prompts.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_prompts = _load_prompts()


def get_mapgpt_query_messages(user_question: str) -> List[Dict[str, str]]:
    """Build the query prompt messages list.

    Args:
        user_question: The user's natural language question.

    Returns:
        List of message dicts with role and content.
    """
    system_prompt = _prompts["query_instructions"]["system"]
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question},
    ]
