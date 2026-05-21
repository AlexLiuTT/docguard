import os
import logging
import docx
from typing import List
from ner_engine import extract_all_entities

logger = logging.getLogger("docguard")

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 100) -> List[str]:
    # 简单的按块划分
    chunks = []
    if len(text) <= chunk_size:
        return [text] if text else []
    
    start = 0
    while start < len(text):
        chunks.append(text[start:start+chunk_size])
        start += chunk_size - overlap
    return chunks

def process_docx(input_path: str, output_path: str):
    logger.info(f"  ▶ 正在处理 Word 文档: {os.path.basename(input_path)}")
    try:
        doc = docx.Document(input_path)
    except Exception as e:
        logger.error(f"  ❌ 读取 {input_path} 失败: {e}")
        return False, ""
    
    # 1. 提取所有纯文本，用于 NER
    full_text = []
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text)
    
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if para.text.strip():
                        full_text.append(para.text)
                        
    raw_text = "\n".join(full_text)
    if not raw_text.strip():
        logger.warning(f"  [警告] {os.path.basename(input_path)} 未提取到文本。")
        return False, ""
    
    # 2. 分块送给大模型进行实体识别
    text_chunks = chunk_text(raw_text)
    entities = extract_all_entities(text_chunks)
    
    logger.info(f"    ✅ 共找到 {len(entities)} 个敏感实体: {entities[:5]}...")
    
    # 3. 遍历 docx 的所有 Runs，执行精准文本替换
    def replace_in_runs(paragraphs):
        for para in paragraphs:
            for run in para.runs:
                if run.text:
                    for entity in entities:
                        if entity in run.text:
                            run.text = run.text.replace(entity, "[脱敏]")

    replace_in_runs(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                replace_in_runs(cell.paragraphs)
    
    # 4. 保存文件
    doc.save(output_path)
    
    clean_text = raw_text
    for entity in entities:
        clean_text = clean_text.replace(entity, "[脱敏]")
        
    return True, clean_text
