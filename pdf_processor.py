import fitz
import os
import logging
from typing import List
from ner_engine import extract_all_entities
from docx_processor import chunk_text
from ocr_engine import extract_text_and_boxes

logger = logging.getLogger("docguard")

def process_pdf(input_path: str, output_path: str):
    logger.info(f"  ▶ 正在处理 PDF 文档: {os.path.basename(input_path)}")
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        logger.error(f"  ❌ 读取 {input_path} 失败: {e}")
        return False, ""
        
    full_text = []
    # 记录每页的 OCR 结果，结构: {page_idx: [{"text": ..., "box": ...}]}
    page_ocr_results = {}
    
    for i, page in enumerate(doc):
        text = page.get_text()
        if len(text.strip()) < 10:
            # 可能是图片型 PDF，触发 OCR 回退
            logger.info(f"    [OCR] 第 {i+1} 页未提取到足够原生文本，触发视觉 OCR 扫描...")
            pix = page.get_pixmap()
            img_bytes = pix.tobytes("png")
            ocr_res = extract_text_and_boxes(img_bytes)
            
            page_text = "\n".join([item["text"] for item in ocr_res])
            full_text.append(page_text)
            page_ocr_results[i] = ocr_res
        else:
            full_text.append(text)
            
    raw_text = "\n".join(full_text)
    if not raw_text.strip():
        logger.warning(f"  [警告] {os.path.basename(input_path)} 未提取到文本，OCR 识别也失败。")
        return False, ""
        
    # 2. 分块送给大模型进行实体识别
    text_chunks = chunk_text(raw_text)
    entities = extract_all_entities(text_chunks)
    logger.info(f"    ✅ 共找到 {len(entities)} 个敏感实体: {entities[:5]}...")
    
    # 3. 遍历 PDF 页面，对每个实体进行纯黑矩形打码
    for i, page in enumerate(doc):
        for entity in entities:
            # 优先使用原生文本搜索坐标
            text_instances = page.search_for(entity)
            for inst in text_instances:
                page.draw_rect(inst, color=(0,0,0), fill=(0,0,0))
                
            # 如果该页是 OCR 页面，我们从 OCR 的结果中推算坐标打码
            if i in page_ocr_results:
                for item in page_ocr_results[i]:
                    rec_text = item["text"]
                    if entity in rec_text:
                        box = item["box"]
                        # box: [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
                        x_coords = [pt[0] for pt in box]
                        y_coords = [pt[1] for pt in box]
                        x_min, x_max = min(x_coords), max(x_coords)
                        y_min, y_max = min(y_coords), max(y_coords)
                        
                        # 比例估算切割坐标 (特种狙击)
                        start_idx = rec_text.find(entity)
                        char_w = (x_max - x_min) / max(len(rec_text), 1)
                        
                        sub_x_min = x_min + start_idx * char_w
                        sub_x_max = x_min + (start_idx + len(entity)) * char_w
                        
                        rect = fitz.Rect(sub_x_min, y_min, sub_x_max, y_max)
                        page.draw_rect(rect, color=(0,0,0), fill=(0,0,0))
                        
    # 4. 保存输出
    doc.save(output_path)
    doc.close()
    
    clean_text = raw_text
    for entity in entities:
        clean_text = clean_text.replace(entity, "[脱敏]")
        
    return True, clean_text
