"""
placeholder_registry.py — GlobalMapping 类

管理实体→占位符的双向映射，支持按实体类型独立计数、幂等分配、正反向查找和序列化。
"""

from dataclasses import dataclass, field
from typing import Optional

# 实体类型到占位符前缀的映射
TYPE_PREFIX: dict[str, str] = {
    "P":   "P",
    "ORG": "ORG",
    "LOC": "LOC",
    "AMT": "AMT",
    "ID":  "ID",
}


@dataclass
class GlobalMapping:
    session_id: str
    created_at: str
    # key: placeholder (e.g. "[[P001]]"), value: {"original": ..., "type": ...}
    mappings: dict[str, dict] = field(default_factory=dict)
    # 内部：original_text -> placeholder，用于快速反查
    _reverse: dict[str, str] = field(default_factory=dict, repr=False)
    # 各类型当前计数器，初始为 1
    _counters: dict[str, int] = field(
        default_factory=lambda: {k: 1 for k in TYPE_PREFIX}, repr=False
    )

    def get_or_create(self, original: str, entity_type: str) -> str:
        """
        若 original 已在映射中，返回已有占位符（幂等）；
        否则分配下一个可用占位符，写入映射，返回新占位符。
        """
        if original in self._reverse:
            return self._reverse[original]

        prefix = TYPE_PREFIX.get(entity_type, "P")
        counter = self._counters.get(entity_type, 1)
        placeholder = f"[[{prefix}{counter:03d}]]"
        self._counters[entity_type] = counter + 1

        self.mappings[placeholder] = {"original": original, "type": entity_type}
        self._reverse[original] = placeholder
        return placeholder

    def lookup_placeholder(self, original: str) -> Optional[str]:
        """根据原文查找占位符（已有才返回，否则 None）。"""
        return self._reverse.get(original)

    def lookup_original(self, placeholder: str) -> Optional[str]:
        """根据占位符还原原文（不存在则 None）。"""
        entry = self.mappings.get(placeholder)
        return entry["original"] if entry else None

    def to_dict(self) -> dict:
        """序列化为可写入 mapping.json 的 dict，包含 session_id、created_at、mappings 三字段。"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "mappings": self.mappings,
        }
