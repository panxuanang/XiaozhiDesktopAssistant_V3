from __future__ import annotations

import fnmatch
import os
import shutil
from pathlib import Path
from typing import Iterable

from ..action_log import record


def desktop_dir() -> Path:
    return Path.home() / "Desktop"


def resolve_user_path(path: str) -> Path:
    text = path.strip().strip('"').strip("'")
    aliases = {
        "桌面": desktop_dir(),
        "desktop": desktop_dir(),
        "下载": Path.home() / "Downloads",
        "downloads": Path.home() / "Downloads",
        "文档": Path.home() / "Documents",
        "documents": Path.home() / "Documents",
    }
    lowered = text.lower()
    if lowered in aliases:
        return aliases[lowered].expanduser().resolve()
    for key, base in aliases.items():
        if lowered.startswith(key.lower() + "/") or lowered.startswith(key.lower() + "\\"):
            rest = text[len(key):].lstrip("/\\")
            return (base / rest).expanduser().resolve()
    return Path(os.path.expandvars(text)).expanduser().resolve()


def search_files(query: str, root: str = "桌面", max_results: int = 30) -> list[str]:
    base = resolve_user_path(root)
    if not base.exists():
        return []
    q = query.lower().strip()
    results: list[str] = []
    wildcard = any(c in q for c in "*?[]")
    for current, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files + dirs:
            matched = fnmatch.fnmatch(name.lower(), q) if wildcard else q in name.lower()
            if matched:
                results.append(str(Path(current) / name))
                if len(results) >= max_results:
                    record("search_files", {"query": query, "root": str(base)}, detail=f"{len(results)} results")
                    return results
    record("search_files", {"query": query, "root": str(base)}, detail=f"{len(results)} results")
    return results


def create_text_file(path: str, content: str = "", overwrite: bool = False) -> str:
    target = resolve_user_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(f"文件已存在：{target}")
    target.write_text(content, encoding="utf-8")
    record("create_text_file", {"path": str(target)}, detail=f"{len(content)} chars")
    return str(target)


def move_path(source: str, destination: str, overwrite: bool = False) -> str:
    src = resolve_user_path(source)
    dst = resolve_user_path(destination)
    if not src.exists():
        raise FileNotFoundError(src)
    if dst.is_dir():
        dst = dst / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if not overwrite:
            raise FileExistsError(dst)
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    result = shutil.move(str(src), str(dst))
    record("move_path", {"source": str(src), "destination": str(dst)})
    return result


def copy_path(source: str, destination: str, overwrite: bool = False) -> str:
    src = resolve_user_path(source)
    dst = resolve_user_path(destination)
    if not src.exists():
        raise FileNotFoundError(src)
    if dst.is_dir():
        dst = dst / src.name
    if dst.exists() and not overwrite:
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=overwrite)
    else:
        shutil.copy2(src, dst)
    record("copy_path", {"source": str(src), "destination": str(dst)})
    return str(dst)


def delete_path(path: str, confirmed: bool = False) -> str:
    target = resolve_user_path(path)
    if not confirmed:
        return f"CONFIRM_REQUIRED: 删除操作不可逆。请向用户确认后再次调用，并设置 confirmed=true。目标：{target}"
    if not target.exists():
        return f"目标不存在：{target}"
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    record("delete_path", {"path": str(target)}, detail="confirmed")
    return f"已删除：{target}"


def list_directory(path: str = "桌面", max_items: int = 100) -> list[dict[str, object]]:
    root = resolve_user_path(path)
    items = []
    for item in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:max_items]:
        stat = item.stat()
        items.append({
            "name": item.name,
            "path": str(item),
            "is_dir": item.is_dir(),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return items


def organize_by_extension(path: str, confirmed: bool = False) -> str:
    root = resolve_user_path(path)
    if not confirmed:
        return f"CONFIRM_REQUIRED: 将移动 {root} 下的文件到按扩展名分类的子目录。确认后设置 confirmed=true。"
    moved = 0
    for item in list(root.iterdir()):
        if not item.is_file():
            continue
        ext = item.suffix.lower().lstrip(".") or "无扩展名"
        folder = root / ext.upper()
        folder.mkdir(exist_ok=True)
        shutil.move(str(item), str(folder / item.name))
        moved += 1
    record("organize_by_extension", {"path": str(root)}, detail=f"moved={moved}")
    return f"已整理 {moved} 个文件。"
