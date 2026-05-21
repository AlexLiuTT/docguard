import os
import sys
import json
import hashlib
import logging
from pathlib import Path

from docx_processor import process_docx
from pdf_processor import process_pdf
from txt_processor import process_txt
from xlsx_processor import process_xlsx
from pptx_processor import process_pptx
from img_processor import process_img
from quality_checker import check_residual_names

# ================= 核心配置区 =================
SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_FOLDER = SCRIPT_DIR / "input"
OUTPUT_FOLDER = SCRIPT_DIR / "output"
LOG_FOLDER = SCRIPT_DIR / "logs"
PROCESSED_RECORD_FILE = SCRIPT_DIR / ".processed.json"

def setup_logging():
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("docguard")
    logger.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    file_handler = logging.FileHandler(LOG_FOLDER / "docguard.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

def ensure_directories():
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

def compute_file_fingerprint(file_path: Path) -> str:
    """基于文件名、大小和修改时间生成指纹。"""
    stat = file_path.stat()
    raw = f"{file_path.name}|{stat.st_size}|{stat.st_mtime}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()

def load_processed_record() -> dict:
    if PROCESSED_RECORD_FILE.exists():
        try:
            return json.loads(PROCESSED_RECORD_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def save_processed_record(record: dict):
    PROCESSED_RECORD_FILE.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

def process_all_files():
    ensure_directories()
    
    files = [f for f in INPUT_FOLDER.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not files:
        logger.info(f"[提示] 请将待处理的文件放入红区目录：\n{INPUT_FOLDER}")
        return
        
    record = load_processed_record()
    to_process = []
    
    for file_path in files:
        fp = compute_file_fingerprint(file_path)
        if record.get(file_path.name) == fp:
            logger.info(f"  [缓存跳过] {file_path.name} (未修改，已脱敏过)")
        else:
            to_process.append(file_path)
            
    if not to_process:
        logger.info("🎉 所有文件均已处理过，无需重复脱敏。")
        return
        
    logger.info(f"🚀 开始处理 {len(to_process)} 个文件，输出绿区目标：\n{OUTPUT_FOLDER}")
    
    for file_path in to_process:
        ext = file_path.suffix.lower()
        output_filename = f"脱敏_{file_path.name}"
        output_path = OUTPUT_FOLDER / output_filename
        
        success = False
        clean_text = ""
        
        if ext == ".docx":
            success, clean_text = process_docx(str(file_path), str(output_path))
        elif ext == ".pdf":
            success, clean_text = process_pdf(str(file_path), str(output_path))
        elif ext in [".txt", ".md"]:
            success, clean_text = process_txt(str(file_path), str(output_path))
        elif ext == ".xlsx":
            success, clean_text = process_xlsx(str(file_path), str(output_path))
        elif ext == ".pptx":
            success, clean_text = process_pptx(str(file_path), str(output_path))
        elif ext in [".jpg", ".jpeg", ".png"]:
            # 图片格式输出强制设为 PDF
            output_path = output_path.with_suffix(".pdf")
            output_filename = output_path.name
            success, clean_text = process_img(str(file_path), str(output_path))
        elif ext == ".doc":
            logger.warning(f"  [跳过] 不支持老旧的 .doc 格式，请先另存为 .docx：{file_path.name}")
        else:
            logger.warning(f"  [跳过] 暂不支持的文件格式 {ext}: {file_path.name}")
            
        if success:
            logger.info(f"    ✅ 已投递至绿区: {output_filename}")
            
            # 质量校验与 MD 输出
            if clean_text:
                warnings = check_residual_names(clean_text)
                for w in warnings:
                    logger.warning(f"    ⚠️ {w} -> 建议人工复核！")
                
                md_filename = f"脱敏_{file_path.stem}.md"
                md_path = OUTPUT_FOLDER / md_filename
                
                import datetime
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                header = f"---\n原始文件: {file_path.name}\n输出时间: {now_str}\n"
                if warnings:
                    header += f"质量警告: {'; '.join(warnings)}\n"
                header += "---\n\n"
                
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(header + clean_text)
                
                if ext not in [".txt", ".md"]:
                    logger.info(f"    📝 已额外生成纯文本 MD 格式供大模型下游分析: {md_filename}")
            
            # 更新缓存
            record[file_path.name] = compute_file_fingerprint(file_path)
            save_processed_record(record)

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("  DocGuard 守卫版（支持 Word/PDF/Excel/PPT/TXT 原生脱敏）")
    logger.info("=" * 50)
    process_all_files()
    logger.info("🎉 批量脱敏任务结束。")
