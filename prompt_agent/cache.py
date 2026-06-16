"""
prompt_agent/cache.py
---------------------
增量修订基线存储 + 提示词 diff 判据。

替代旧的相似度注入式缓存。每个节点只保存最近一次成功运行的"基线"
（提示词 + 最终输出）。下次运行时与之做 diff：
  - 完全相同        → 直接复用上次输出（零调用）
  - 小改（块数/相似度达标） → 续写式修订，复用上次结果只改动相关部分
  - 大改 / 模式或图片变化   → 冷跑

设计见 docs/incremental_revision_cache.md。
"""

from __future__ import annotations

import difflib
import re
import threading


# ── diff 判据阈值（设计文档 §五/§十） ──────────────────────────────
MAX_EDIT_BLOCKS = 2      # 独立变更块数上限：≈ 改动了几个维度
MIN_SIMILARITY = 0.4     # 词级相似度地板：防止"1 块但近乎整段重写"


# token 切分（diff 用），优先级从上到下：
#   ① 带权重的括号组 (a,b,c:1.2) / (1girl:2) —— 整组作为一个 token（权重作用于整组，
#      改权重或改组内标签都让该 token 变化，指令带上完整的组，避免误解作用范围）
#   ② ASCII 词，可带 :权重 后缀（无括号的 tag:1.2，把权重并入而非拆成 1、2）
#   ③ 每个 CJK 字符单独一个
# 标点、空白作为分隔符被丢弃，不参与 diff（避免标点差异产生伪变更块）。
_TOKEN_RE = re.compile(
    r"\([^()]*:\d+(?:\.\d+)?\)"
    r"|[A-Za-z0-9_]+(?::\d+(?:\.\d+)?)?"
    r"|[一-鿿]"
)


def normalize(text: str) -> str:
    """归一化提示词用于存储 / 完全相同判定：去首尾空白、合并连续空白、小写。"""
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _tokenize(text: str) -> list[tuple]:
    """返回 [(lower, start, end)]，保留原文字符偏移以便回切可读原文。"""
    return [(m.group(0).lower(), m.start(), m.end()) for m in _TOKEN_RE.finditer(text or "")]


def _raw_slice(text: str, toks: list[tuple], i1: int, i2: int) -> str:
    """只回切变更 token 区间本身的原文（不扩展），用于「增加」「删除」指令。

    增/删若像替换那样向两侧扩展到子句，会把相邻的**未变**内容也写进指令
    （如「白发少女→白发蓝瞳少女」误成「增加白发蓝瞳少女」），故增/删不扩展。
    """
    if i1 >= i2:
        return ""
    return text[toks[i1][1]:toks[i2 - 1][2]].strip()


def _clause_slice(text: str, toks: list[tuple], i1: int, i2: int) -> str:
    """把变更 token 区间扩展到所在「子句」后回切原文，用于消歧。

    子句 = 无间隔字符的连续 token 串（被标点/空白隔断即为边界）。
    只给「白」在「白发，白色水手服」里无法定位是哪一个，扩展为「白发」即可定位。
    """
    if i1 >= i2:
        return ""
    while i1 > 0 and text[toks[i1 - 1][2]:toks[i1][1]] == "":
        i1 -= 1
    while i2 < len(toks) and text[toks[i2 - 1][2]:toks[i2][1]] == "":
        i2 += 1
    return text[toks[i1][1]:toks[i2 - 1][2]].strip()


def compute_edit(old_text: str, new_text: str) -> dict:
    """对比新旧提示词。返回 {continue, blocks, ratio, instruction}。

    continue=True 表示属"小改"，可走增量修订续写；
    instruction 为给模型的自然语言改动说明。
    """
    old_toks = _tokenize(old_text)
    new_toks = _tokenize(new_text)
    sm = difflib.SequenceMatcher(
        a=[t[0] for t in old_toks], b=[t[0] for t in new_toks], autojunk=False,
    )
    opcodes = sm.get_opcodes()
    ratio = sm.ratio()

    changes = []
    new_terms = []   # 新增/替换后的目标词，供 Low 续写做精准查找（删除不产生）
    blocks = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        blocks += 1
        if tag == "replace":
            # 替换：两侧都扩展到子句，对称展示，使改动可唯一定位（消歧）
            old_seg = _clause_slice(old_text, old_toks, i1, i2)
            new_seg = _clause_slice(new_text, new_toks, j1, j2)
            changes.append(f"把「{old_seg}」改为「{new_seg}」")
            new_terms.append(new_seg)
        elif tag == "delete":
            # 增/删：只取变更 token 本身，不扩展到相邻未变内容
            changes.append(f"删除「{_raw_slice(old_text, old_toks, i1, i2)}」")
        elif tag == "insert":
            new_seg = _raw_slice(new_text, new_toks, j1, j2)
            changes.append(f"增加「{new_seg}」")
            new_terms.append(new_seg)

    # 同一子句内的多处改动扩展后可能产生重复指令，去重保序
    seen = set()
    changes = [c for c in changes if not (c in seen or seen.add(c))]
    seen2 = set()
    new_terms = [t for t in new_terms if t and not (t in seen2 or seen2.add(t))]

    can_continue = 0 < blocks <= MAX_EDIT_BLOCKS and ratio >= MIN_SIMILARITY
    return {
        "continue": can_continue,
        "blocks": blocks,
        "ratio": ratio,
        "instruction": "；".join(changes),
        "new_terms": new_terms,
    }


# ═══════════════════════════════════════════════════════════════════
# 基线存储：每节点保存最近一次运行（进程内，按 unique_id 键）
# ═══════════════════════════════════════════════════════════════════

class BaselineStore:
    """每个节点只保存最近一次成功运行的基线。

    Baseline 字段：
        norm_input  归一化提示词（完全相同判定 + diff 对比）
        raw_input   原始提示词（续写时作为 [user] 上文）
        output      上次最终输出全文（续写时作为 [assistant] 上文）
        mode        "NewBie" / "Anima"
        has_image   上次是否带图（回退判定）
    """

    def __init__(self):
        self._by_node: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, node_id) -> dict | None:
        if node_id is None:
            return None
        with self._lock:
            return self._by_node.get(str(node_id))

    def put(self, node_id, baseline: dict):
        if node_id is None:
            return
        with self._lock:
            self._by_node[str(node_id)] = baseline

    def clear(self):
        with self._lock:
            self._by_node.clear()


_baseline_store: BaselineStore | None = None


def get_baseline_store() -> BaselineStore:
    global _baseline_store
    if _baseline_store is None:
        _baseline_store = BaselineStore()
    return _baseline_store
