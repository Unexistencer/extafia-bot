import random
from dataclasses import dataclass, field
from typing import Dict, List, Iterator, Tuple

from service.enchant_rules import get_affix_index_table, get_affix_data
from constants import Special_Vaal

# ────────────────────────── Structure ────────────────────────────

@dataclass
class Fighter:
    user_id: int
    name: str
    base: int = 0
    final: int = 0
    testicular: int = 1
    affix_ids: List[int] = field(default_factory=list)
    affix_vals: List[int] = field(default_factory=list)
    is_corrupted: bool = False
    financial_pct: int = 0
    scavenge_pct: int = 100
    show_head: bool = True
    log: List[str] = field(default_factory=list)


def effective_len(f: "Fighter") -> int:
    return max(0, f.final + f.testicular)


def render_cock_display(f: "Fighter") -> str:
    head = "8" if f.testicular > 0 and f.show_head else ""
    return f"{head}{'='*max(0, f.final)}D"


# check affix via id
def reverse_index() -> Dict[int, Tuple[str, str]]:
    rev: Dict[int, Tuple[str, str]] = {}
    table = get_affix_index_table()
    for t in ("prefix", "suffix"):
        for name, idx in table[t].items():
            rev[idx] = (t, name)
    return rev


def iter_affixes(f: Fighter, rev_index: Dict[int, Tuple[str, str]]) -> Iterator[Tuple[str, str, int, dict]]:
    for i, affix_id in enumerate(f.affix_ids):
        meta = rev_index.get(affix_id)
        if not meta:
            continue
        typ, name = meta
        val = f.affix_vals[i] if i < len(f.affix_vals) else 0
        data = get_affix_data(typ, name, "en") or {}
        yield typ, name, int(val) if val is not None else 0, data


# debuff target
def _pick_others(n: int, me: int, k: int) -> List[int]:
    others = [i for i in range(n) if i != me]
    random.shuffle(others)
    return others[: min(k, len(others))]

def _pick_self(me: int) -> List[int]:
    return [me]

def _pick_except_self(n: int, me: int) -> List[int]:
    return [i for i in range(n) if i != me]


# ─────────────────────────────────────────────────────────────────────
# Phase 1: reroll
def phase_rerolls(fighters: List[Fighter], rev_index: Dict[int, Tuple[str, str]]):
    n = len(fighters)
    # prefix: take the highest
    for f in fighters:
        for typ, name, val, data in iter_affixes(f, rev_index):
            if typ != "prefix":
                continue
            if data.get("mode") == "reroll_high" or data.get("reroll") == "high" or name in ("Gambler", "Lucky"):
                r = random.randint(0, 20)
                old = f.final
                f.final = max(f.final, r)
                f.log.append(f"[Prefix] {name}: 高擲比較 {old} vs {r} → {f.final}")

    # suffix: take the lowest
    for idx, s in enumerate(fighters):
        for typ, name, val, data in iter_affixes(s, rev_index):
            if typ != "suffix":
                continue
            if data.get("mode") == "reroll_low" or name in ("Fear", "Feargeist"):
                k = max(1, int(val) or 1)
                targets = _pick_others(n, idx, k)
                for t in targets:
                    victim = fighters[t]
                    r = random.randint(0, 20)
                    old = victim.final
                    victim.final = min(victim.final, r)
                    s.log.append(f"[Suffix] {name}: 讓 {victim.name} 低擲比較 {old} vs {r} → {victim.final}")
                    victim.log.append(f"[Debuff] 來自 {s.name}: {name} 低擲（{old} vs {r} → {victim.final}）")


# Phase 1.5: Mirrored
def phase_mirrored(fighters: List[Fighter], rev_index: Dict[int, Tuple[str, str]], center: int = 10):
    for f in fighters:
        for typ, name, val, data in iter_affixes(f, rev_index):
            if typ != "prefix" or name != "Mirrored":
                continue
            x = int(f.final)
            if val == Special_Vaal.success:
                if x < center:
                    new = (center - x) * 3
                    f.log.append(f"[Prefix] Mirrored(success): {x} → {new}")
                    f.final = max(0, new)
            elif val == Special_Vaal.nerf:
                new = 2 * center - x
                f.log.append(f"[Prefix] Mirrored(nerf): {x} → {new}")
                f.final = max(0, new)
            else:
                if x < center:
                    new = 2 * center - x
                    f.log.append(f"[Prefix] Mirrored: {x} → {new}")
                    f.final = max(0, new)


# Phase 2/5: Meisterdieb
def phase_meisterdieb(fighters: List[Fighter], rev_index: Dict[int, Tuple[str, str]], stage: str):
    n = len(fighters)
    if n <= 1:
        return

    for idx, f in enumerate(fighters):
        for typ, name, val, data in iter_affixes(f, rev_index):
            if typ != "suffix" or name != "Meisterdieb":
                continue

            if val == Special_Vaal.success:
                if stage != "final":
                    continue
                targets = _pick_others(n, idx, 1)
                if not targets:
                    continue
                t = targets[0]
                other = fighters[t]
                f.final, other.final = other.final, f.final
                f.log.append(f"[Suffix] Meisterdieb: 與 {other.name} 交換最終長度 → 自己 {f.final}")
                other.log.append(f"[Debuff] 被 {f.name} 交換最終長度 → 自己 {other.final}")

            elif val == Special_Vaal.nerf:
                if stage != "initial":
                    continue
                others = [i for i in range(n) if i != idx]
                random.shuffle(others)
                if len(others) >= 2:
                    a, b = others[0], others[1]
                    A, B = fighters[a], fighters[b]
                    A.final, B.final = B.final, A.final
                    f.log.append(f"[Suffix] Meisterdieb: 令 {A.name} 與 {B.name} 交換初始長度")
                    A.log.append(f"[Debuff] 受 {f.name} 影響: 與 {B.name} 交換初始長度 → 自己 {A.final}")
                    B.log.append(f"[Debuff] 受 {f.name} 影響: 與 {A.name} 交換初始長度 → 自己 {B.final}")
                else:
                    targets = _pick_others(n, idx, 1)
                    if targets:
                        t = targets[0]
                        other = fighters[t]
                        f.final, other.final = other.final, f.final
                        f.log.append(f"[Suffix] Meisterdieb: 與 {other.name} 交換初始長度 → 自己 {f.final}")
                        other.log.append(f"[Debuff] 被 {f.name} 交換初始長度 → 自己 {other.final}")

            else:
                if stage != "initial":
                    continue
                targets = _pick_others(n, idx, 1)
                if not targets:
                    continue
                t = targets[0]
                other = fighters[t]
                f.final, other.final = other.final, f.final
                f.log.append(f"[Suffix] Meisterdieb: 與 {other.name} 交換初始長度 → 自己 {f.final}")
                other.log.append(f"[Debuff] 被 {f.name} 交換初始長度 → 自己 {other.final}")


# Phase 3: add/sub (and Torsion)
def phase_add_sub(fighters: List[Fighter], rev_index: Dict[int, Tuple[str, str]]):
    n = len(fighters)

    # 3a) add
    for f in fighters:
        cnt = len(fighters)
        for typ, name, val, data in iter_affixes(f, rev_index):
            if typ != "prefix":
                continue
            mode = data.get("mode")
            if mode == "plus":
                if name == "Dueling":
                    if cnt == 2:
                        f.final += val
                        f.log.append(f"[Prefix] Dueling: +{val} (2 人對決)")
                else:
                    f.final += val
                    f.log.append(f"[Prefix] {name}: +{val}")

    # 3b) sub
    to_minus: List[tuple[int, List[int], int, str]] = []
    torsion_targets: List[tuple[int, int]] = []

    for idx, s in enumerate(fighters):
        for typ, name, val, data in iter_affixes(s, rev_index):
            if typ != "suffix":
                continue
            if name == "Spear":
                targets = _pick_others(n, idx, 1)
                if targets:
                    to_minus.append((idx, targets, int(val), name))
            elif name == "Trampler":
                targets = _pick_others(n, idx, val)
                if targets:
                    to_minus.append((idx, targets, int(val), name))
            elif name == "Torsion":
                if val == Special_Vaal.success:
                    targets = _pick_except_self(n, idx)
                elif val == Special_Vaal.nerf:
                    targets = _pick_self(idx)
                else:
                    targets = _pick_others(n, idx, 1)
                for t in targets:
                    torsion_targets.append((idx, t))

    # apply minus
    for src, targets, delta, name in to_minus:
        s = fighters[src]
        for t in targets:
            v = fighters[t]
            old = v.final
            v.final = max(0, v.final - delta)
            s.log.append(f"[Suffix] {name}: 對 {v.name} -{delta}")
            v.log.append(f"[Debuff] 被 {s.name} {name}: {old}→{v.final}")

    # Torsion
    for src, t in torsion_targets:
        s = fighters[src]
        v = fighters[t]
        v.testicular = max(0, v.testicular - 1)
        v.show_head = False
        s.log.append(f"[Suffix] Torsion: 扭掉 {v.name} 的 8（有效長度 -1）")
        v.log.append(f"[Debuff] 被 {s.name} Torsion（有效長度 -1）")


# Phase 4: multiply
def phase_multiply(fighters: List[Fighter], rev_index: Dict[int, Tuple[str, str]]):
    for f in fighters:
        for typ, name, val, data in iter_affixes(f, rev_index):
            if typ != "prefix":
                continue
            if data.get("mode") == "multiply":
                old = f.final
                f.final = max(0, f.final * max(0, int(val)))
                f.log.append(f"[Prefix] {name}: ×{val}（{old}→{f.final}）")


# financial
def extract_financial_flags(f: Fighter, rev_index: Dict[int, Tuple[str, str]]):
    f.financial_pct = 0
    f.scavenge_pct = 100
    for i, affix_id in enumerate(f.affix_ids):
        meta = rev_index.get(affix_id)
        if not meta:
            continue
        typ, name = meta
        if typ == "prefix" and name == "Financial":
            data = get_affix_data("prefix", name, "en")
            val = f.affix_vals[i] if i < len(f.affix_vals) else 0
            scale = (data or {}).get("value_display_scale", 1)
            f.financial_pct += int(val * scale)
            f.log.append(f"[Bonus] Financial: 勝利額外 +{f.financial_pct}%")
        elif typ == "suffix" and name == "Scavenger":
            data = get_affix_data("suffix", name, "en")
            val = f.affix_vals[i] if i < len(f.affix_vals) else 0
            scale = (data or {}).get("value_display_scale", 1)
            f.scavenge_pct = min(f.scavenge_pct, int(val * scale))
            f.log.append(f"[Bonus] Scavenger: 失敗只損失 {f.scavenge_pct}%")
