"""
restorer.py — 还原核心

读取 mapping.json，将脱敏文档中的占位符逆向替换回原始实体文本。
"""

import re
import json
import logging
from pathlib import Path

import docx as python_docx

from .placeholder_registry import GlobalMapping

logger = logging.getLogger("docguard")


def load_mapping(session_dir: Path) -> GlobalMapping:
    """读取并解析 mapping.json，重建反向索引；失败时抛出 ValueError。"""
    mapping_path = session_dir / "mapping.json"
    try:
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"mapping.json 读取失败: {e}")
    gm = GlobalMapping(
        session_id=data["session_id"],
        created_at=data["created_at"],
        mappings=data["mappings"],
    )
    for ph, entry in data["mappings"].items():
        gm._reverse[entry["original"]] = ph
    return gm


def restore_text(text: str, mapping: GlobalMapping) -> str:
    """将文本中所有已知占位符替换回原文，按占位符长度降序处理。"""
    sorted_placeholders = sorted(mapping.mappings.keys(), key=len, reverse=True)
    result = text
    for placeholder in sorted_placeholders:
        original = mapping.lookup_original(placeholder)
        if original is not None:
            result = result.replace(placeholder, original)
    return result


def check_residual_placeholders(text: str, mapping: GlobalMapping) -> list[str]:
    """检查文本中残留的未知占位符，返回警告消息列表。"""
    pattern = re.compile(r"\[\[[A-Z]+\d{3}\]\]")
    found = set(pattern.findall(text))
    unknown = found - set(mapping.mappings.keys())
    return [f"未知占位符保留原样: {ph}" for ph in unknown]


def restore_docx(input_path: str, output_path: str, mapping: GlobalMapping) -> bool:
    """在 run 级别将占位符替换回原文，保留排版样式，保存文件。"""
    try:
        doc = python_docx.Document(input_path)
    except Exception as e:
        logger.error(f"  ❌ 读取 {input_path} 失败: {e}")
        return False

    sorted_phs = sorted(mapping.mappings.keys(), key=len, reverse=True)

    def restore_runs(paragraphs):
        for para in paragraphs:
            for run in para.runs:
                if run.text:
                    for ph in sorted_phs:
                        original = mapping.lookup_original(ph)
                        if original and ph in run.text:
                            run.text = run.text.replace(ph, original)

    restore_runs(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                restore_runs(cell.paragraphs)

    doc.save(output_path)
    return True
