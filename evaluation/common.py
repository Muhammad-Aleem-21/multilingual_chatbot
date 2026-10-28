"""
common.py  -  tiny helpers shared by the three evaluation scripts.
"""

import json
from collections import defaultdict
from pathlib import Path


def load_json(path: Path):
    """Read a .json file and return it as normal Python lists / dictionaries."""
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save_json(data, path: Path) -> None:
    """Write Python data to a .json file (ensure_ascii=False keeps Urdu readable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def group_by(rows: list, key: str) -> dict:
    """Split a list of dictionaries into {value_of_key: [rows...]}."""
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return groups


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.1f}%" if whole else "  n/a "
