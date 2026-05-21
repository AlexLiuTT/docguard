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
