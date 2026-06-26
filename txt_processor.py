import os
import logging
from typing import List
from ner_engine import extract_all_entities
from docx_processor import chunk_text

logger = logging.getLogger("docguard")

def process_txt(input_path: str, output_path: str):
    logger.info(f"  ▶ 正在处理纯文本/Markdown文档: {os.path.basename(input_path)}")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
    except Exception as e:
        logger.error(f"  ❌ 读取 {input_path} 失败: {e}")
        return False, ""
        
    if not raw_text.strip():
        logger.warning(f"  [警告] {os.path.basename(input_path)} 文本为空。")
        return False, ""
        
    # 分块送给大模型进行实体识别
    text_chunks = chunk_text(raw_text)
    entities = extract_all_entities(text_chunks)
    logger.info(f"    ✅ 共找到 {len(entities)} 个敏感实体: {entities[:5]}...")
    
    # 执行替换
    clean_text = raw_text
    for entity in entities:
        clean_text = clean_text.replace(entity, "[脱敏]")
        
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(clean_text)
        
    return True, clean_text

from ner_engine import extract_entities_with_types
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from reversible.placeholder_registry import GlobalMapping


def process_txt_reversible(input_path: str, output_path: str, mapping: "GlobalMapping") -> tuple[bool, str]:
    logger.info(f"  ▶ 正在可逆脱敏纯文本/Markdown文档: {os.path.basename(input_path)}")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
    except Exception as e:
        logger.error(f"  ❌ 读取 {input_path} 失败: {e}")
        return False, ""

    if not raw_text.strip():
        logger.warning(f"  [警告] {os.path.basename(input_path)} 文本为空。")
        return False, ""

    # 分块调用带类型的实体识别
    text_chunks = chunk_text(raw_text)
    entities_with_types = extract_entities_with_types(text_chunks)
    logger.info(f"    ✅ 共找到 {len(entities_with_types)} 个实体（含类型）")

    # 对每个实体分配占位符
    sorted_entities = [
        (original, mapping.get_or_create(original, entity_type), entity_type)
        for original, entity_type in entities_with_types
    ]
    # entities_with_types 已按长度降序排列，sorted_entities 顺序一致

    # 执行字符串替换
    anonymized_text = raw_text
    for original, placeholder, _ in sorted_entities:
        anonymized_text = anonymized_text.replace(original, placeholder)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(anonymized_text)

    return True, anonymized_text
