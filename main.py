import os
import sys
import logging
from pathlib import Path
from docx_processor import process_docx
from pdf_processor import process_pdf
from txt_processor import process_txt
from xlsx_processor import process_xlsx
from pptx_processor import process_pptx

# ================= 核心配置区 =================
# 动态定位本脚本所在目录
SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_FOLDER = SCRIPT_DIR / "input"
OUTPUT_FOLDER = SCRIPT_DIR / "output"
LOG_FOLDER = SCRIPT_DIR / "logs"

def setup_logging():
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("docguard")
    logger.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 添加文件日志
    file_handler = logging.FileHandler(LOG_FOLDER / "docguard.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

def ensure_directories():
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    
def process_all_files():
    ensure_directories()
    
    files = [f for f in INPUT_FOLDER.iterdir() if f.is_file() and not f.name.startswith(".")]
    
    if not files:
        logger.info(f"[提示] 请将待处理的 Word/PDF/PPT/Excel/TXT 文件放入红区目录：\n{INPUT_FOLDER}")
        return
        
    logger.info(f"🚀 开始处理 {len(files)} 个文件，输出绿区目标：\n{OUTPUT_FOLDER}")
    
    for file_path in files:
        ext = file_path.suffix.lower()
        output_filename = f"脱敏_{file_path.name}"
        output_path = OUTPUT_FOLDER / output_filename
        
        success = False
        if ext == ".docx":
            success = process_docx(str(file_path), str(output_path))
        elif ext == ".pdf":
            success = process_pdf(str(file_path), str(output_path))
        elif ext in [".txt", ".md"]:
            success = process_txt(str(file_path), str(output_path))
        elif ext == ".xlsx":
            success = process_xlsx(str(file_path), str(output_path))
        elif ext == ".pptx":
            success = process_pptx(str(file_path), str(output_path))
        elif ext == ".doc":
            logger.warning(f"  [跳过] 不支持老旧的 .doc 格式，请先另存为 .docx：{file_path.name}")
        else:
            logger.warning(f"  [跳过] 暂不支持的文件格式 {ext}: {file_path.name}")
            
        if success:
            logger.info(f"    ✅ 已投递至绿区: {output_filename}")

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("  DocGuard 守卫版（支持 Word/PDF/Excel/PPT/TXT 原生脱敏）")
    logger.info("=" * 50)
    process_all_files()
    logger.info("🎉 批量脱敏任务结束。")
