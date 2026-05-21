import logging
from rapidocr_onnxruntime import RapidOCR

logger = logging.getLogger("docguard")

_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        logger.info("    [OCR] 首次调用，正在后台加载极速 OCR 模型库...")
        _ocr_engine = RapidOCR()
    return _ocr_engine

def extract_text_and_boxes(img_bytes: bytes):
    """
    输入图像字节流，返回文本列表和坐标盒子
    返回格式:
    [
      {
        "text": "张三",
        "box": [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]
      }, ...
    ]
    """
    engine = get_ocr_engine()
    result, elapse = engine(img_bytes)
    
    extracted = []
    if result:
        for item in result:
            dt_box = item[0]
            rec_text = item[1]
            extracted.append({"text": rec_text, "box": dt_box})
            
    return extracted
