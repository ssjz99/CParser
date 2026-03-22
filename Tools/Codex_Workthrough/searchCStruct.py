"""Search and extract C structure definitions with libclang.

This module exposes a single public function, ``searchCStruct``, that scans
``.c`` and ``.h`` files and returns matching structure metadata.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from clang import cindex
from clang.cindex import Cursor, CursorKind


def _configure_libclang(logger: logging.Logger) -> None:
    """Configure libclang DLL path for environments where autodiscovery fails."""
    try:
        cindex.Config.set_compatibility_check(False)
        if getattr(cindex.Config, "loaded", False):
            return
        dll_path = Path(cindex.__file__).resolve().parent / "native" / "libclang.dll"
        if dll_path.exists():
            cindex.Config.set_library_file(str(dll_path))
            logger.debug("Configured libclang from %s", dll_path)
    except Exception:
        logger.debug("libclang configuration failed")
        logger.debug(traceback.format_exc())


def _setup_logger(log_dir: Optional[str]) -> logging.Logger:
    """Create a timestamped logger for searchCStruct."""
    logger_name = f"searchCStruct_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    output_dir = Path(log_dir) if log_dir else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = output_dir / f"searchCStruct_{stamp}.log"
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def _discover_source_files(src_path: Path) -> List[Path]:
    """Find C source/header files from a directory or a single file path."""
    if src_path.is_file():
        return [src_path] if src_path.suffix.lower() in {".c", ".h"} else []
    return sorted(
        [p for p in src_path.rglob("*") if p.is_file() and p.suffix.lower() in {".c", ".h"}]
    )


def _read_text(path: Path) -> str:
    """Read file text with UTF-8 fallback behavior."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _extract_definition_text(file_path: Path, cursor: Cursor) -> str:
    """Extract the exact source range for a struct cursor."""
    content = _read_text(file_path)
    start = cursor.extent.start.offset
    end = cursor.extent.end.offset
    if start < 0 or end <= start or end > len(content):
        return ""
    return content[start:end].strip()


def _extract_definition_by_name(file_path: Path, struct_name: str) -> str:
    """Extract `struct <name> { ... };` from raw source preserving directives."""
    text = _read_text(file_path)
    marker = f"struct {struct_name}"
    start = text.find(marker)
    if start < 0:
        return ""

    brace_start = text.find("{", start)
    if brace_start < 0:
        return ""

    depth = 0
    end = -1
    for idx in range(brace_start, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                semi = text.find(";", idx)
                end = semi + 1 if semi >= 0 else idx + 1
                break
    if end <= start:
        return ""
    return text[start:end].strip()


def _extract_members(struct_cursor: Cursor) -> List[Dict[str, str]]:
    """Extract member name/type list from a struct cursor."""
    members: List[Dict[str, str]] = []
    for child in struct_cursor.get_children():
        if child.kind == CursorKind.FIELD_DECL:
            members.append({"name": child.spelling, "type": child.type.spelling})
    return members


def _struct_name_from_cursor(cursor: Cursor) -> str:
    """Resolve a structure name from STRUCT_DECL or TYPEDEF_DECL cursor."""
    if cursor.kind == CursorKind.STRUCT_DECL:
        return cursor.spelling or ""
    if cursor.kind == CursorKind.TYPEDEF_DECL:
        return cursor.spelling or ""
    return ""


def _iter_struct_candidates(cursor: Cursor):
    """Yield candidate struct-related cursors recursively."""
    if cursor.kind in {CursorKind.STRUCT_DECL, CursorKind.TYPEDEF_DECL}:
        yield cursor
    for child in cursor.get_children():
        yield from _iter_struct_candidates(child)


def _resolve_struct_cursor(candidate: Cursor) -> Optional[Cursor]:
    """Return the underlying STRUCT_DECL cursor for a candidate node."""
    if candidate.kind == CursorKind.STRUCT_DECL:
        return candidate if candidate.is_definition() else None
    if candidate.kind == CursorKind.TYPEDEF_DECL:
        for child in candidate.get_children():
            if child.kind == CursorKind.STRUCT_DECL and child.is_definition():
                return child
    return None


def _log_structure_diagram(logger: logging.Logger, name: str, members: List[Dict[str, str]]) -> None:
    """Log a simple structure text diagram."""
    logger.info("struct %s", name)
    logger.info("{")
    for item in members:
        logger.info("  %s %s;", item["type"], item["name"])
    logger.info("}")


def searchCStruct(
    src_path: str,
    target_list: List[str],
    include_path_list: List[str],
    log_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search C structure definitions from files.

    Args:
        src_path: Source folder or file to scan.
        target_list: Structure names to match.
        include_path_list: Include paths used for clang parsing.
        log_dir: Optional folder for log file output.

    Returns:
        A list of dictionaries:
        - name (str)
        - file (str)
        - line (int)
        - column (int)
        - definition (str)
        - members (List[Dict[str, str]])

    Raises:
        No public exceptions; failures are logged and an empty list is returned.

    Example:
        >>> searchCStruct("./src", ["Config"], ["./src"])
    """
    logger = _setup_logger(log_dir)
    logger.info("searchCStruct started: src=%s targets=%s includes=%s", src_path, target_list, include_path_list)

    try:
        src = Path(src_path).resolve()
        if not src.exists():
            logger.error("Source path does not exist: %s", src)
            return []
        if not target_list:
            logger.error("target_list is empty")
            return []

        files = _discover_source_files(src)
        logger.info("Discovered %d source files", len(files))

        target_set = set(target_list)
        _configure_libclang(logger)
        index = cindex.Index.create()
        results: List[Dict[str, Any]] = []

        clang_args = ["-x", "c", "-std=c11"] + [f"-I{Path(p)}" for p in include_path_list]

        for file_path in files:
            logger.info("Parsing file: %s", file_path)
            try:
                tu = index.parse(str(file_path), args=clang_args)
                for diag in tu.diagnostics:
                    logger.warning("clang diagnostic in %s: %s", file_path, diag)

                for candidate in _iter_struct_candidates(tu.cursor):
                    struct_cursor = _resolve_struct_cursor(candidate)
                    if struct_cursor is None:
                        continue

                    name = _struct_name_from_cursor(candidate) or _struct_name_from_cursor(struct_cursor)
                    if name not in target_set:
                        continue

                    members = _extract_members(struct_cursor)
                    definition_file = (
                        Path(struct_cursor.location.file.name).resolve()
                        if struct_cursor.location.file
                        else file_path
                    )
                    definition_text = _extract_definition_by_name(definition_file, name)
                    if not definition_text:
                        definition_text = _extract_definition_text(definition_file, struct_cursor)
                    record = {
                        "name": name,
                        "file": str(definition_file),
                        "line": int(struct_cursor.location.line),
                        "column": int(struct_cursor.location.column),
                        "definition": definition_text,
                        "members": members,
                    }

                    if not any(
                        r["name"] == record["name"] and r["file"] == record["file"] and r["line"] == record["line"]
                        for r in results
                    ):
                        results.append(record)
                        _log_structure_diagram(logger, record["name"], members)
            except Exception:
                logger.error("Failed to parse file: %s", file_path)
                logger.debug(traceback.format_exc())

        logger.info("searchCStruct complete: found %d structures", len(results))
        return results
    except Exception:
        logger.error("Unhandled error in searchCStruct")
        logger.debug(traceback.format_exc())
        return []
