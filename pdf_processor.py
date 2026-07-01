import fitz
import os
import logging
from typing import List, TYPE_CHECKING
from ner_engine import extract_all_entities, extract_entities_with_types
from docx_processor import chunk_text
from ocr_engine import extract_text_and_boxes

if TYPE_CHECKING:
    from reversible.placeholder_registry import GlobalMapping

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


def process_pdf_reversible(input_path: str, output_path: str, mapping: "GlobalMapping") -> tuple[bool, str]:
    """
    PDF 可逆脱敏：使用 redaction 真正删除原文，再叠加占位符文本。
    处理跨行实体：空白归一化后搜索。
    """
    logger.info(f"  ▶ 正在可逆脱敏 PDF 文档: {os.path.basename(input_path)}")
    try:
        doc = fitz.open(input_path)
    except Exception as e:
        logger.error(f"  ❌ 读取 {input_path} 失败: {e}")
        return False, ""

    full_text = []
    page_ocr_results = {}

    for i, page in enumerate(doc):
        text = page.get_text()
        if len(text.strip()) < 10:
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
        logger.warning(f"  [警告] {os.path.basename(input_path)} 未提取到文本。")
        return False, ""

    # 分块调用带类型的实体识别
    text_chunks = chunk_text(raw_text)
    entities_with_types = extract_entities_with_types(text_chunks)
    logger.info(f"    ✅ 共找到 {len(entities_with_types)} 个实体（含类型）")

    # 分配占位符
    sorted_entities = [
        (original, mapping.get_or_create(original, entity_type), entity_type)
        for original, entity_type in entities_with_types
    ]

    import re as _re
    _ws_re = _re.compile(r'\s+')

    # 遍历 PDF 页面：先收集所有 redaction，再统一 apply，最后插入占位符
    for i, page in enumerate(doc):
        # 收集本页所有需要 redact 的 (rect, placeholder) 对
        page_redactions: list[tuple] = []  # [(rect, placeholder), ...]

        for original, placeholder, entity_type in sorted_entities:
            # 1. 原生文本搜索
            text_instances = page.search_for(original)
            for inst in text_instances:
                page_redactions.append((inst, placeholder))

            # 1b. 跨行实体：用空白归一化搜索
            if not text_instances and _ws_re.search(original):
                # 尝试去掉空白后搜索
                compact = _ws_re.sub('', original)
                if compact and len(compact) >= 2:
                    compact_instances = page.search_for(compact)
                    for inst in compact_instances:
                        page_redactions.append((inst, placeholder))

            # 2. OCR 页面：按比例估算坐标
            if i in page_ocr_results:
                for item in page_ocr_results[i]:
                    rec_text = item["text"]
                    # 归一化后匹配
                    if _ws_re.sub('', original) in _ws_re.sub('', rec_text):
                        box = item["box"]
                        x_coords = [pt[0] for pt in box]
                        y_coords = [pt[1] for pt in box]
                        x_min, x_max = min(x_coords), max(x_coords)
                        y_min, y_max = min(y_coords), max(y_coords)

                        start_idx = _ws_re.sub('', rec_text).find(_ws_re.sub('', original))
                        compact_rec = _ws_re.sub('', rec_text)
                        compact_orig = _ws_re.sub('', original)
                        char_w = (x_max - x_min) / max(len(compact_rec), 1)

                        sub_x_min = x_min + start_idx * char_w
                        sub_x_max = x_min + (start_idx + len(compact_orig)) * char_w
                        ocr_rect = fitz.Rect(sub_x_min, y_min, sub_x_max, y_max)
                        page_redactions.append((ocr_rect, placeholder))

        if not page_redactions:
            continue

        # 统一添加 redaction 注解
        for rect, _placeholder in page_redactions:
            page.add_redact_annot(rect, fill=(1, 1, 1))

        # 一次性 apply — 真正删除底层文字
        page.apply_redactions()

        # apply 之后插入占位符文本
        for rect, placeholder in page_redactions:
            fontsize = max(rect.height * 0.75, 5.0)
            try:
                page.insert_text(
                    fitz.Point(rect.x0, rect.y1 - 1),
                    placeholder,
                    fontsize=fontsize,
                    color=(0, 0, 0),
                )
            except Exception:
                pass

    doc.save(output_path)
    doc.close()

    # 生成脱敏后的 clean text（空白归一化替换）
    anonymized_clean_text = raw_text
    for original, placeholder, _ in sorted_entities:
        # 先尝试直接替换
        anonymized_clean_text = anonymized_clean_text.replace(original, placeholder)
        # 如果直接替换没生效（跨行），用归一化替换
        if original in raw_text and placeholder not in anonymized_clean_text:
            compact_orig = _ws_re.sub('', original)
            compact_text = _ws_re.sub('', anonymized_clean_text)
            anonymized_clean_text = compact_text.replace(compact_orig, placeholder)

    return True, anonymized_clean_text
