"""
prompt_agent/cache.py
---------------------
提示词缓存模块。

匹配策略：字符集 Jaccard 相似度（中文语义感知，O(n+m)）。
持久化：有界 JSON 全量快照，跨 ComfyUI 会话保留。
"""

from __future__ import annotations

import collections
import json
import os
import re
import threading
import tempfile


# ── 缓存文件路径 ──────────────────────────────────────────────────

_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".prompt_cache.json")


# ═══════════════════════════════════════════════════════════════════
# PromptCache
# ═══════════════════════════════════════════════════════════════════

class PromptCache:
    """提示词缓存：LRU 淘汰 + 字符集 Jaccard 匹配 + 磁盘持久化。

    使用字符级 unigram Jaccard：中文语序宽松，阈值 0.35 平衡召回率与精确度。
    """

    def __init__(self, max_size: int = 50, lookup_threshold: float = 0.35,
                 dedup_threshold: float = 0.92):
        self._cache: collections.OrderedDict = collections.OrderedDict()
        self._max_size = max_size
        self._lookup_threshold = lookup_threshold
        self._dedup_threshold = dedup_threshold
        self._lock = threading.Lock()

    # ── 字符集 Jaccard ───────────────────────────────────────────

    @staticmethod
    def _to_charset(text: str) -> set[str]:
        """提取文本的字符集合。保留中文字符、ASCII 字母数字。"""
        return set(re.sub(r"[^一-鿿\w]", "", text.lower()))

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        """字符集 Jaccard 相似度。"""
        set_a = PromptCache._to_charset(a)
        set_b = PromptCache._to_charset(b)
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    # ── 查询与存储 ──────────────────────────────────────────────

    def lookup(self, user_input: str) -> dict | None:
        """查找最相似缓存条目。短输入走 exact match。"""
        if not self._cache or not user_input:
            return None

        inp = user_input.strip()
        if len(inp) <= 5:
            entry = self._cache.get(inp)
            if entry is not None:
                self._cache.move_to_end(inp)
                return {"tags": entry["tags"], "mode": entry["mode"]}
            return None

        best_key, best_score = None, 0.0
        with self._lock:
            for key in self._cache:
                score = self._jaccard(inp, key)
                if score > best_score:
                    best_key, best_score = key, score

        if best_key is None or best_score < self._lookup_threshold:
            return None

        with self._lock:
            entry = self._cache.pop(best_key)
            self._cache[best_key] = entry
        return {"tags": entry["tags"], "mode": entry["mode"]}

    def store(self, user_input: str, tags: list, mode: str):
        """存储条目。近乎相同（≥0.92）则覆盖旧条目。"""
        if not user_input or not tags:
            return

        with self._lock:
            for key in list(self._cache.keys()):
                if self._jaccard(user_input, key) >= self._dedup_threshold:
                    del self._cache[key]
                    break

            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[user_input] = {"tags": tags, "mode": mode}

        self._flush_to_disk()

    def clear(self):
        with self._lock:
            self._cache.clear()
        self._flush_to_disk()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    # ── 磁盘持久化 ──────────────────────────────────────────────

    def _flush_to_disk(self):
        """全量写入 JSON（temp file + rename 原子替换）。所有异常静默，不影响主流程。"""
        try:
            with self._lock:
                entries = [[k, v] for k, v in self._cache.items()]
            data = json.dumps(entries, ensure_ascii=False, indent=2)
            d = os.path.dirname(_CACHE_FILE)
            fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, _CACHE_FILE)
        except Exception:
            pass

    def _load_from_disk(self):
        """从 JSON 快照恢复缓存。"""
        if not os.path.exists(_CACHE_FILE):
            return
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            try:
                os.remove(_CACHE_FILE)
            except OSError:
                pass
            return
        with self._lock:
            for item in entries:
                if not isinstance(item, list) or len(item) != 2:
                    continue
                key, value = item
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                if "tags" not in value or "mode" not in value:
                    continue
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = value


# ═══════════════════════════════════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════════════════════════════════

_prompt_cache: PromptCache | None = None


def get_cache() -> PromptCache:
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = PromptCache(max_size=50)
        _prompt_cache._load_from_disk()
    return _prompt_cache


def reset_cache():
    global _prompt_cache
    if _prompt_cache is not None:
        _prompt_cache.clear()
    _prompt_cache = PromptCache(max_size=50)
    _prompt_cache._load_from_disk()


# ═══════════════════════════════════════════════════════════════════
# 标签提取工具
# ═══════════════════════════════════════════════════════════════════


def extract_tags_from_output(xml_out: str, mode: str) -> list[str]:
    if not xml_out or not xml_out.strip():
        return []
    if mode == "Anima":
        return _extract_anima_tags(xml_out)
    return _extract_newbie_tags(xml_out)


def _extract_newbie_tags(xml_string: str) -> list[str]:
    from lxml import etree
    tags = []
    try:
        root = etree.fromstring(xml_string.encode("utf-8"))
    except etree.XMLSyntaxError:
        parser = etree.XMLParser(recover=True)
        try:
            root = etree.fromstring(xml_string.encode("utf-8"), parser=parser)
        except Exception:
            return []
    _collect_leaf_text(root, tags)
    result = []
    for text in tags:
        for part in re.split(r"[,\n]+", text):
            tag = part.strip().rstrip(",")
            if not tag:
                continue
            if _is_placeholder(tag):
                continue
            if tag.startswith("(") and ")" in tag:
                continue
            tag = re.sub(r"[:：]\d+\.?\d*$", "", tag)
            tag = tag.strip()
            if tag and len(tag) > 1:
                result.append(tag)
    return _deduplicate_preserve_order(result)


def _collect_leaf_text(element, accumulator: list):
    children = list(element)
    if not children:
        text = (element.text or "").strip()
        if text:
            accumulator.append(text)
    else:
        for child in children:
            _collect_leaf_text(child, accumulator)
        tail = (element.tail or "").strip()
        if tail:
            accumulator.append(tail)


def _is_placeholder(text: str) -> bool:
    placeholders = {
        "...", "角色名", "人数标签", "画风标签", "背景标签",
        "画面情绪、氛围标签", "各种物品", "其它标签", "其他标签",
        "英文场景描述", "性别标签", "外貌特征", "衣着",
        "表情", "动作", "位置", "画师标签",
    }
    if text in placeholders:
        return True
    if len(text) > 8 and re.search(r"[，。；：]", text):
        return True
    return False


def _extract_anima_tags(xml_out: str) -> list[str]:
    parts = xml_out.split("\n\n", 1)
    tag_block = parts[0] if parts else xml_out
    tags = []
    for tag in tag_block.split(","):
        tag = tag.strip()
        if not tag:
            continue
        if " " in tag and len(tag) > 40:
            continue
        tags.append(tag)
    return _deduplicate_preserve_order(tags)


def format_cached_tags(tags: list) -> str:
    parts = []
    for t in tags:
        if isinstance(t, dict) and t.get('c'):
            parts.append(f'{t["t"]}【{t["c"]}】')
        elif isinstance(t, dict):
            parts.append(t.get('t', str(t)))
        else:
            parts.append(str(t))
    return ', '.join(parts)


def cached_tags_plain(tags: list) -> list:
    return [t['t'] if isinstance(t, dict) else t for t in tags]


def build_tag_entry(tag: str, cn_name: str = '') -> dict:
    first_cn = cn_name.split(',')[0].strip() if cn_name else ''
    return {'t': tag, 'c': first_cn}


def _deduplicate_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
