from __future__ import annotations
import json
import random
from typing import Dict, List, Tuple, Optional
from functools import lru_cache

ENCHANTMENTS_PATH = "data/enchantments.json"

# local cache
_ENCHANTMENTS: Dict = {}
_VERSION: int = 0  # +1 when reload, make lru_cache unavailable

def load_enchantments(path: Optional[str] = None) -> None:
    global _ENCHANTMENTS, _VERSION
    p = path or ENCHANTMENTS_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            _ENCHANTMENTS = json.load(f)
            _VERSION += 1  # make all version unavailable
    except FileNotFoundError:
        print(f"[ERROR] {p} not found.")
        _ENCHANTMENTS = {}
        _VERSION += 1

def _ensure_loaded():
    if not _ENCHANTMENTS:
        load_enchantments()

def get_affix_data(affix_type: str, name: str, language: str = "en") -> Optional[Dict]:
    _ensure_loaded()
    data = _ENCHANTMENTS.get(affix_type, {}).get(name)
    if not data:
        return None
    return {
        "type": data["type"],
        "mode": data.get("mode"),
        "value_range": data.get("value_range"),
        "value": data.get("value"),
        "vaal_success": data.get("vaal_success"),
        "vaal_nerf": data.get("vaal_nerf"),
        "name": data["name"][language],
        "description": data["description"],
    }

@lru_cache(maxsize=1)
def _get_affix_index_table(version: int) -> Dict[str, Dict[str, int]]:
    _ensure_loaded()
    table = {"prefix": {}, "suffix": {}}
    idx = 0
    for name in _ENCHANTMENTS.get("prefix", {}):
        table["prefix"][name] = idx; idx += 1
    for name in _ENCHANTMENTS.get("suffix", {}):
        table["suffix"][name] = idx; idx += 1
    return table

def get_affix_index_table() -> Dict[str, Dict[str, int]]:
    return _get_affix_index_table(_VERSION)

@lru_cache(maxsize=1)
def _get_reverse_index_table(version: int) -> Dict[int, Tuple[str, str]]:
    rev: Dict[int, Tuple[str, str]] = {}
    index_table = _get_affix_index_table(version)
    for t in ("prefix", "suffix"):
        for name, idx in index_table[t].items():
            rev[idx] = (t, name)
    return rev

def get_reverse_index_table() -> Dict[int, Tuple[str, str]]:
    return _get_reverse_index_table(_VERSION)

def get_affix_index(affix_type: str, name: str) -> int:
    return get_affix_index_table()[affix_type][name]

def roll_affix_value(affix: dict) -> int:
    if "value_range" in affix:
        lo, hi = affix["value_range"]
        return random.randint(lo, hi)
    if "value" in affix:
        return int(affix["value"])
    return 0

def generate_random_affix_data() -> Tuple[List[int], List[int], bool]:
    _ensure_loaded()
    prefix_pool = list(_ENCHANTMENTS.get("prefix", {}).keys())
    suffix_pool = list(_ENCHANTMENTS.get("suffix", {}).keys())

    num_prefix = random.randint(0, 2)
    num_suffix = random.randint(1, 2) if num_prefix == 0 else random.randint(0, 2)

    selected_prefixes = random.sample(prefix_pool, min(num_prefix, len(prefix_pool)))
    selected_suffixes = random.sample(suffix_pool, min(num_suffix, len(suffix_pool)))

    affix_ids, affix_values = [], []
    for name in selected_prefixes:
        idx = get_affix_index("prefix", name)
        val = roll_affix_value(_ENCHANTMENTS["prefix"][name])
        affix_ids.append(idx); affix_values.append(val)
    for name in selected_suffixes:
        idx = get_affix_index("suffix", name)
        val = roll_affix_value(_ENCHANTMENTS["suffix"][name])
        affix_ids.append(idx); affix_values.append(val)

    is_corrupted = False
    return affix_ids, affix_values, is_corrupted

def vaal_enchant(user_data: Dict) -> Tuple[List[int], List[int], bool]:
    import random
    _ensure_loaded()
    affix_ids = list(user_data.get("affixes", []))
    affix_values = list(user_data.get("affix_values", []))
    is_corrupted = True

    rev = get_reverse_index_table()

    i = 0
    while i < len(affix_ids):
        affix_id = affix_ids[i]
        current_val = affix_values[i] if i < len(affix_values) else 0
        result = random.choice(["success", "nerf", "nothing", "lost"])

        info = rev.get(affix_id)
        if not info:
            i += 1; continue
        affix_type, name = info
        data = get_affix_data(affix_type, name, language="en")
        if not data:
            i += 1; continue

        if result == "lost":
            affix_ids.pop(i)
            if i < len(affix_values): affix_values.pop(i)
            continue
        elif result == "success":
            vaal_rule = data.get("vaal_success") or {}
        elif result == "nerf":
            vaal_rule = data.get("vaal_nerf") or {}
        else:
            vaal_rule = {}

        new_val = current_val
        rng = vaal_rule.get("range")
        if isinstance(rng, list) and len(rng) == 2:
            new_val += random.randint(rng[0], rng[1])
        if "value" in vaal_rule and isinstance(vaal_rule["value"], int):
            new_val = vaal_rule["value"]
        affix_values[i] = new_val
        i += 1

    return affix_ids, affix_values, is_corrupted

def get_user_affixes_text(affix_ids: List[int], affix_values: List[int], *, lang="en", is_corrupted=False) -> str:
    _ensure_loaded()
    if not affix_ids:
        return _ENCHANTMENTS.get("none", {}).get(lang, "")

    reverse_table = get_reverse_index_table()
    title = "**"
    if is_corrupted:
        title += _ENCHANTMENTS.get("corrupted", {}).get(lang, "")
    descriptions: List[str] = []

    for idx, affix_id in enumerate(affix_ids):
        info = reverse_table.get(affix_id)
        if not info: continue
        affix_type, name = info
        data = get_affix_data(affix_type, name, lang)
        if not data: continue

        title += f"{data['name']}"
        value = affix_values[idx] if idx < len(affix_values) else 0

        match value:
            case 20000:
                text = data["description"]["vaal_success"][lang]
            case 30000:
                text = data["description"]["vaal_nerf"][lang]
            case _:
                text = data["description"][lang].format(value=value)
        descriptions.append(text)

    title += "**"
    if not descriptions:
        return _ENCHANTMENTS.get("none", {}).get(lang, "")
    return "\n".join([title, *descriptions])
