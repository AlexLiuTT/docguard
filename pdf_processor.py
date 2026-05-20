import os
import logging
import fitz  # PyMuPDF
from typing import List
from ner_engine import extract_all_entities
from docx_processor import chunk_text

logger = logging.getLogger("docguard")

def process_pdf(input_path: str, output_path: str):
    logger.info(f"  ▶ 正在处理 PDF 文档: {os.path.basename(input_path)}")
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        logger.error(f"  ❌ 读取 {input_path} 失败: {e}")
        return False
        
    # 1. 提取文本用于 NER
    full_text = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            full_text.append(text)
            
    raw_text = "\n".join(full_text)
    if not raw_text.strip():
        logger.warning(f"  [警告] {os.path.basename(input_path)} 未提取到文本（可能是纯图扫描件，当前版本需可提取文本）。")
        return False
        
    # 2. 分块送给大模型进行实体识别
    text_chunks = chunk_text(raw_text)
    entities = extract_all_entities(text_chunks)
    logger.info(f"    ✅ 共找到 {len(entities)} 个敏感实体: {entities[:5]}...")
    
    # 3. 逐页搜索实体并打码
    redact_color = (0, 0, 0) # 纯黑色遮挡
    
    for page in doc:
        for entity in entities:
            # 搜索当前页面上该实体的所有出现位置坐标
            rects = page.search_for(entity)
            for rect in rects:
                # 添加打码标注
                # fill: 填充颜色
                page.add_redact_annot(rect, fill=redact_color)
        # 真正应用打码
        page.apply_redactions()
        
    # 4. 保存输出
    doc.save(output_path)
    doc.close()
    return True
