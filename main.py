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

from reversible.session_manager import create_session, list_sessions, get_session_files
from reversible.anonymizer import _build_global_mapping, _save_mapping
from reversible.restorer import load_mapping, restore_text, restore_docx, check_residual_placeholders
from docx_processor import process_docx_reversible
from txt_processor import process_txt_reversible
from xlsx_processor import process_xlsx_reversible

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

def show_menu() -> str:
    while True:
        print("\n" + "=" * 50)
        print("  DocGuard 文档守卫")
        print("=" * 50)
        print("  1. 普通打码（不可逆）")
        print("  2. 可逆脱敏（生成 mapping）")
        print("  3. 还原文档（从 mapping 恢复）")
        print("=" * 50)
        choice = input("请输入选项编号（1/2/3）：").strip()
        if choice in ("1", "2", "3"):
            return choice
        print("[错误] 无效输入，请输入 1、2 或 3。")


def run_reversible_anonymization():
    ensure_directories()
    files = [f for f in INPUT_FOLDER.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not files:
        logger.info(f"[提示] 请将待处理的文件放入红区目录：\n{INPUT_FOLDER}")
        return

    session_dir = create_session()
    logger.info(f"🔑 已创建 Session: {session_dir.name}")

    mapping = _build_global_mapping(session_dir)
    success_list, fail_list = [], []

    for file_path in files:
        ext = file_path.suffix.lower()
        output_filename = f"脱敏_{file_path.name}"
        output_path = session_dir / output_filename
        success = False
        try:
            if ext == ".docx":
                success, _ = process_docx_reversible(str(file_path), str(output_path), mapping)
            elif ext in [".txt", ".md"]:
                success, _ = process_txt_reversible(str(file_path), str(output_path), mapping)
            elif ext == ".xlsx":
                success, _ = process_xlsx_reversible(str(file_path), str(output_path), mapping)
            else:
                logger.warning(f"  [跳过] 可逆脱敏暂不支持 {ext}: {file_path.name}")
                continue
        except Exception as e:
            logger.error(f"  ❌ 处理 {file_path.name} 失败: {e}")
            fail_list.append(file_path.name)
            continue

        if success:
            _save_mapping(mapping, session_dir)
            success_list.append(file_path.name)
            logger.info(f"    ✅ 已投递至 Session: {output_filename}")
        else:
            fail_list.append(file_path.name)

    logger.info(f"\n📊 可逆脱敏完成 — 成功: {len(success_list)}, 失败: {len(fail_list)}")
    if fail_list:
        logger.warning(f"  失败文件: {fail_list}")
    logger.info(f"  mapping.json 已保存至: {session_dir / 'mapping.json'}")


def run_restore():
    sessions = list_sessions()
    if not sessions:
        print("\n[提示] 未找到可用的脱敏记录，请先执行可逆脱敏。")
        return

    print("\n可用的脱敏 Session（最新在前）：")
    for i, s in enumerate(sessions, 1):
        print(f"  {i}. {s.name}")

    while True:
        raw = input("请选择 Session 编号：").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(sessions):
            session_dir = sessions[int(raw) - 1]
            break
        print("[错误] 无效编号，请重新输入。")

    try:
        mapping = load_mapping(session_dir)
    except ValueError as e:
        print(f"[错误] {e}")
        return

    files = get_session_files(session_dir)
    if not files:
        print("[提示] 该 Session 内没有可还原的文件。")
        return

    print("\n可还原的文件：")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f.name}")
    print(f"  0. 还原全部")

    while True:
        raw = input("请选择文件编号（0 为全部）：").strip()
        if raw == "0":
            targets = files
            break
        elif raw.isdigit() and 1 <= int(raw) <= len(files):
            targets = [files[int(raw) - 1]]
            break
        print("[错误] 无效编号，请重新输入。")

    for file_path in targets:
        ext = file_path.suffix.lower()
        output_path = session_dir / f"还原_{file_path.name}"
        try:
            if ext == ".docx":
                ok = restore_docx(str(file_path), str(output_path), mapping)
            elif ext in [".txt", ".md"]:
                text = file_path.read_text(encoding="utf-8")
                restored = restore_text(text, mapping)
                warnings = check_residual_placeholders(restored, mapping)
                for w in warnings:
                    logger.warning(f"    ⚠️  {w}")
                output_path.write_text(restored, encoding="utf-8")
                ok = True
            elif ext == ".xlsx":
                print(f"  [提示] .xlsx 文件暂不支持还原，请手动处理：{file_path.name}")
                continue
            else:
                print(f"  [跳过] 不支持还原格式 {ext}: {file_path.name}")
                continue
        except Exception as e:
            logger.error(f"  ❌ 还原 {file_path.name} 失败: {e}")
            continue

        if ok:
            logger.info(f"    ✅ 还原完成: {output_path.name}")
        else:
            logger.error(f"    ❌ 还原失败: {file_path.name}")


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
    choice = show_menu()
    if choice == "1":
        process_all_files()
        logger.info("🎉 批量脱敏任务结束。")
    elif choice == "2":
        run_reversible_anonymization()
    elif choice == "3":
        run_restore()
