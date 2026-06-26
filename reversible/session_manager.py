from pathlib import Path
from datetime import datetime

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "output"


def create_session() -> Path:
    """在 output/ 下创建带时间戳的 session 文件夹，返回其 Path。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = OUTPUT_ROOT / f"session_{ts}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def list_sessions() -> list[Path]:
    """
    扫描 output/ 下所有以 session_ 开头且包含 mapping.json 的子目录，
    按创建时间降序返回（最新在前）。
    """
    if not OUTPUT_ROOT.exists():
        return []
    sessions = [
        d for d in OUTPUT_ROOT.iterdir()
        if d.is_dir()
        and d.name.startswith("session_")
        and (d / "mapping.json").exists()
    ]
    return sorted(sessions, key=lambda d: d.stat().st_ctime, reverse=True)


def get_session_files(session_dir: Path) -> list[Path]:
    """返回 session 文件夹内所有可还原文件（.docx / .md / .txt），排除还原_ 前缀的文件。"""
    exts = {".docx", ".md", ".txt"}
    return [
        f for f in session_dir.iterdir()
        if f.is_file()
        and f.suffix.lower() in exts
        and not f.name.startswith("还原_")
    ]
