"""
anonymizer.py — 可逆脱敏核心

负责：调用 NER 引擎（带类型分类）→ 占位符分配 → 文本替换 → 输出文件 → 持久化 mapping.json。
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime, timezone

from .placeholder_registry import GlobalMapping

logger = logging.getLogger("docguard")

MAPPING_FILE = "mapping.json"


def _build_global_mapping(session_dir: Path) -> GlobalMapping:
    """新建或从磁盘加载一个 session 的 GlobalMapping。

    若 mapping.json 已存在则加载并重建反向索引和计数器；否则新建。
    """
    mapping_path = session_dir / MAPPING_FILE
    session_id = session_dir.name
    if mapping_path.exists():
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
        gm = GlobalMapping(
            session_id=session_id,
            created_at=data["created_at"],
            mappings=data["mappings"],
        )
        # 重建反向索引和计数器
        for ph, entry in data["mappings"].items():
            gm._reverse[entry["original"]] = ph
            etype = entry["type"]
            m = re.search(r"(\d+)\]\]$", ph)
            if m:
                num = int(m.group(1))
                if num >= gm._counters.get(etype, 1):
                    gm._counters[etype] = num + 1
        return gm
    return GlobalMapping(
        session_id=session_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _save_mapping(mapping: GlobalMapping, session_dir: Path) -> None:
    """将 GlobalMapping 序列化写入 mapping.json（UTF-8，缩进 2，ensure_ascii=False）。"""
    mapping_path = session_dir / MAPPING_FILE
    mapping_path.write_text(
        json.dumps(mapping.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _replace_text(text: str, sorted_entities: list[tuple[str, str, str]]) -> str:
    """
    sorted_entities: [(original, placeholder, type), ...]，已按 original 长度降序。
    对文本执行全量字符串替换，返回脱敏后文本。
    """
    result = text
    for original, placeholder, _ in sorted_entities:
        result = result.replace(original, placeholder)
    return result


def _replace_in_docx_runs(doc, sorted_entities: list[tuple[str, str, str]]) -> None:
    """在 run 级别对 docx 执行精准替换，保留样式。"""
    def replace_runs(paragraphs):
        for para in paragraphs:
            for run in para.runs:
                if run.text:
                    for original, placeholder, _ in sorted_entities:
                        if original in run.text:
                            run.text = run.text.replace(original, placeholder)

    replace_runs(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                replace_runs(cell.paragraphs)
