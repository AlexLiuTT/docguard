import fitz
import os
import logging
from pdf_processor import process_pdf

logger = logging.getLogger("docguard")

def process_img(input_path: str, output_path: str):
    logger.info(f"  ▶ 正在处理图片文件: {os.path.basename(input_path)}")
    try:
        # 用 PyMuPDF 打开图片，无损转为一页 PDF
        img_doc = fitz.open(input_path)
        pdf_bytes = img_doc.convert_to_pdf()
        img_doc.close()
        
        # 将 PDF 保存到临时路径
        temp_pdf = input_path + ".temp.pdf"
        with open(temp_pdf, 'wb') as f:
            f.write(pdf_bytes)
            
    except Exception as e:
        logger.error(f"  ❌ 读取图片 {input_path} 失败: {e}")
        return False, ""
        
    # 复用强大的 PDF OCR 与打码逻辑
    success, clean_text = process_pdf(temp_pdf, output_path)
    
    # 清理临时文件
    if os.path.exists(temp_pdf):
        os.remove(temp_pdf)
        
    return success, clean_text
