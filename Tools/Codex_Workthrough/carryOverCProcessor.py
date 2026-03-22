"""Carry over C preprocessor context for struct variables into `.mod` outputs.

This module intentionally preserves original files and writes any processed
content to a sibling `.mod` file.
"""

from __future__ import annotations

import logging
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
    """Create a timestamped logger for carryOverCProcessor."""
    logger_name = f"carryOverCProcessor_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    output_dir = Path(log_dir) if log_dir else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = output_dir / f"carryOverCProcessor_{stamp}.log"
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


def _has_preprocessor_guards(definition: str) -> bool:
    """Check whether struct definition includes preprocessor directives."""
    if not definition:
        return False
    directives = ("#if", "#ifdef", "#ifndef", "#elif", "#else", "#endif")
    return any(token in definition for token in directives)


def _iter_variables(cursor: Cursor):
    """Yield variable declarations recursively."""
    if cursor.kind == CursorKind.VAR_DECL:
        yield cursor
    for child in cursor.get_children():
        yield from _iter_variables(child)


def _base_struct_type_name(type_spelling: str) -> str:
    """Normalize a variable type to its struct name when possible."""
    raw = " ".join(type_spelling.replace("*", " ").split())
    if raw.startswith("struct "):
        return raw[len("struct ") :].strip()
    return raw.strip()


def _has_initializer(var_cursor: Cursor) -> bool:
    """Check whether a variable declaration includes an initializer."""
    for child in var_cursor.get_children():
        if child.kind in {CursorKind.INIT_LIST_EXPR, CursorKind.UNEXPOSED_EXPR, CursorKind.INTEGER_LITERAL, CursorKind.STRING_LITERAL}:
            return True
    return False


def _write_mod_file(source_file: Path, content: str, logger: logging.Logger) -> Path:
    """Write modified content to `.mod` file next to original file."""
    mod_file = source_file.with_suffix(source_file.suffix + ".mod")
    mod_file.write_text(content, encoding="utf-8")
    logger.info("Wrote .mod file: %s", mod_file)
    logger.info("Original file preserved: %s", source_file)
    return mod_file


def _is_field_declaration(line: str) -> bool:
    """Return True when a line looks like a plain struct field declaration."""
    stripped = line.strip().split("//", 1)[0].strip()
    if not stripped:
        return False
    if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        return False
    if stripped.startswith("#"):
        return False
    if "{" in stripped or "}" in stripped:
        return False
    return stripped.endswith(";")


def _field_name_from_declaration(line: str) -> str:
    """Extract field name from a declaration line."""
    cleaned = line.strip().split("//", 1)[0].strip()
    if not cleaned.endswith(";"):
        return ""
    cleaned = cleaned[:-1].strip()
    match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*$", cleaned)
    return match.group(1) if match else ""


def _parse_guard_layout(definition: str) -> List[Dict[str, Any]]:
    """Parse struct definition into plain/guarded field count segments."""
    open_brace = definition.find("{")
    close_brace = definition.rfind("}")
    if open_brace < 0 or close_brace <= open_brace:
        return []

    body = definition[open_brace + 1 : close_brace]
    segments: List[Dict[str, Any]] = []
    plain_count = 0
    guard: Optional[Dict[str, Any]] = None

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("#if ", "#ifdef ", "#ifndef ")):
            if plain_count > 0:
                segments.append({"kind": "plain", "count": plain_count})
                plain_count = 0
            if guard is None:
                guard = {"kind": "guard", "start": line, "end": "#endif", "count": 0}
            continue
        if line.startswith("#endif"):
            if guard is not None:
                guard["end"] = line
                segments.append(guard)
                guard = None
            continue
        if _is_field_declaration(line):
            field_name = _field_name_from_declaration(line)
            if guard is None:
                plain_count += 1
            else:
                guard["count"] += 1
                if field_name:
                    guard.setdefault("fields", []).append(field_name)

    if guard is not None:
        segments.append(guard)
    if plain_count > 0:
        segments.append({"kind": "plain", "count": plain_count})
    return segments


def _split_initializer_entries(initializer_body: str) -> List[str]:
    """Split top-level initializer entries by commas, respecting nesting/strings."""
    entries: List[str] = []
    current: List[str] = []
    depth = 0
    in_string = False
    in_char = False
    escape = False

    for ch in initializer_body:
        if in_string or in_char:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif in_string and ch == '"':
                in_string = False
            elif in_char and ch == "'":
                in_char = False
            continue

        if ch == '"':
            in_string = True
            current.append(ch)
            continue
        if ch == "'":
            in_char = True
            current.append(ch)
            continue
        if ch == "{":
            depth += 1
            current.append(ch)
            continue
        if ch == "}":
            depth -= 1
            current.append(ch)
            continue
        if ch == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                entries.append(token)
            current = []
            continue
        current.append(ch)

    tail = "".join(current).strip()
    if tail:
        entries.append(tail)
    return entries


def _find_initializer_span(decl_text: str) -> Optional[Dict[str, int]]:
    """Locate the initializer braces span inside a variable declaration text."""
    open_brace = decl_text.find("{")
    if open_brace < 0:
        return None
    depth = 0
    close_brace = -1
    for idx in range(open_brace, len(decl_text)):
        ch = decl_text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                close_brace = idx
                break
    if close_brace <= open_brace:
        return None
    return {"open": open_brace, "close": close_brace}


def _apply_guard_layout_to_declaration(decl_text: str, segments: List[Dict[str, Any]]) -> str:
    """Apply parsed guard layout to a struct variable initializer declaration."""
    span = _find_initializer_span(decl_text)
    if not span or not segments:
        return decl_text

    init_body = decl_text[span["open"] + 1 : span["close"]]
    if "#if" in init_body:
        return decl_text

    entries = _split_initializer_entries(init_body)
    expected = sum(int(seg.get("count", 0)) for seg in segments)
    if not entries or expected <= 0 or len(entries) != expected:
        return decl_text

    entry_indent = "    "
    for line in init_body.splitlines():
        stripped = line.strip()
        if stripped:
            entry_indent = line[: len(line) - len(line.lstrip())] or "    "
            break

    rebuilt_lines: List[str] = []
    idx = 0
    for seg in segments:
        count = int(seg.get("count", 0))
        if count <= 0:
            continue
        if seg.get("kind") == "guard":
            rebuilt_lines.append(f"{entry_indent}{seg.get('start', '#ifdef UNKNOWN')}")
        for _ in range(count):
            if idx >= len(entries):
                return decl_text
            rebuilt_lines.append(f"{entry_indent}{entries[idx]},")
            idx += 1
        if seg.get("kind") == "guard":
            rebuilt_lines.append(f"{entry_indent}{seg.get('end', '#endif')}")

    if idx != len(entries):
        return decl_text

    for i in range(len(rebuilt_lines) - 1, -1, -1):
        line = rebuilt_lines[i].rstrip()
        if line.startswith("#"):
            continue
        if line.endswith(","):
            rebuilt_lines[i] = line[:-1]
        break

    new_body = "\n" + "\n".join(rebuilt_lines) + "\n"
    return decl_text[: span["open"] + 1] + new_body + decl_text[span["close"] :]


def _apply_guards_to_designated_fields(decl_text: str, struct_layout_map: Dict[str, List[Dict[str, Any]]]) -> str:
    """Insert guard blocks around designated initializer lines (e.g. `.readings =`)."""
    blocks: List[Dict[str, str]] = []
    for segments in struct_layout_map.values():
        for seg in segments:
            if seg.get("kind") != "guard":
                continue
            for field in seg.get("fields", []):
                blocks.append(
                    {
                        "field": field,
                        "start": str(seg.get("start", "#ifdef UNKNOWN")),
                        "end": str(seg.get("end", "#endif")),
                    }
                )

    if not blocks:
        return decl_text

    lines = decl_text.splitlines()
    for block in blocks:
        pattern = re.compile(rf"^\s*\.{re.escape(block['field'])}\s*=")
        matches = [i for i, line in enumerate(lines) if pattern.search(line)]
        if not matches:
            continue

        first = matches[0]
        last = matches[-1]

        prev_nonempty = first - 1
        while prev_nonempty >= 0 and not lines[prev_nonempty].strip():
            prev_nonempty -= 1
        if prev_nonempty >= 0 and lines[prev_nonempty].strip() == block["start"]:
            continue

        indent = lines[first][: len(lines[first]) - len(lines[first].lstrip())] or "    "
        lines.insert(first, f"{indent}{block['start']}")
        lines.insert(last + 2, f"{indent}{block['end']}")

    result = "\n".join(lines)
    if decl_text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def carryOverCProcessor(target_variable_list: List[Dict[str, Any]], log_dir: Optional[str] = None) -> Dict[str, Any]:
    """Process structure variables and generate `.mod` files.

    The processor validates target structure metadata, detects structure
    definitions with preprocessor guards, and identifies struct-typed variables
    with initializers. Matching files are written to `.mod` files while original
    source files remain untouched.

    Args:
        target_variable_list: Structure search output dictionaries.
        log_dir: Optional folder for log output.

    Returns:
        Dictionary with status, file and count details.

    Raises:
        No public exceptions; failures are logged and included in return details.
    """
    logger = _setup_logger(log_dir)
    logger.info("carryOverCProcessor started with %d target entries", len(target_variable_list) if target_variable_list else 0)

    result: Dict[str, Any] = {
        "success": False,
        "processed_files": [],
        "total_structures": 0,
        "total_variables": 0,
        "details": {"matched_structs": [], "matched_variables": [], "errors": []},
    }

    try:
        if not isinstance(target_variable_list, list) or not target_variable_list:
            logger.error("target_variable_list must be a non-empty list")
            return result

        struct_entries = [
            item
            for item in target_variable_list
            if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("file"), str)
        ]
        if not struct_entries:
            logger.error("No valid structure entries found")
            return result

        result["total_structures"] = len(struct_entries)
        struct_layout_map: Dict[str, List[Dict[str, Any]]] = {}
        for item in struct_entries:
            name = item["name"]
            definition = item.get("definition", "")
            if not _has_preprocessor_guards(definition):
                continue
            layout = _parse_guard_layout(definition)
            if layout:
                struct_layout_map[name] = layout

        guarded_structs: Set[str] = set(struct_layout_map.keys())
        if not guarded_structs:
            logger.warning("No structures with preprocessor guards found")
            return result

        source_dirs = {Path(item["file"]).resolve().parent for item in struct_entries}
        all_files: List[Path] = []
        for directory in source_dirs:
            all_files.extend(
                sorted(
                    [
                        p
                        for p in directory.rglob("*")
                        if p.is_file() and p.suffix.lower() in {".c", ".h"}
                    ]
                )
            )
        all_files = sorted(set(all_files))
        _configure_libclang(logger)
        index = cindex.Index.create()

        for source_file in all_files:
            if not source_file.exists() or source_file.suffix.lower() not in {".c", ".h"}:
                continue

            try:
                tu = index.parse(str(source_file), args=["-x", "c", "-std=c11"])
                for diag in tu.diagnostics:
                    logger.warning("clang diagnostic in %s: %s", source_file, diag)

                file_matched = False
                for var_cursor in _iter_variables(tu.cursor):
                    struct_name = _base_struct_type_name(var_cursor.type.spelling)
                    if struct_name not in guarded_structs:
                        continue
                    if not _has_initializer(var_cursor):
                        continue

                    file_matched = True
                    result["total_variables"] += 1
                    result["details"]["matched_structs"].append(struct_name)
                    result["details"]["matched_variables"].append(var_cursor.spelling)
                    logger.info("Matched variable %s of struct %s in %s", var_cursor.spelling, struct_name, source_file)

                if file_matched:
                    content = source_file.read_text(encoding="utf-8", errors="replace")
                    replacements: List[Dict[str, Any]] = []
                    for var_cursor in _iter_variables(tu.cursor):
                        struct_name = _base_struct_type_name(var_cursor.type.spelling)
                        if not _has_initializer(var_cursor):
                            continue
                        start = int(var_cursor.extent.start.offset)
                        end = int(var_cursor.extent.end.offset)
                        if start < 0 or end <= start or end > len(content):
                            continue
                        original_decl = content[start:end]
                        updated_decl = original_decl
                        if struct_name in guarded_structs:
                            updated_decl = _apply_guard_layout_to_declaration(
                                updated_decl,
                                struct_layout_map.get(struct_name, []),
                            )
                        updated_decl = _apply_guards_to_designated_fields(
                            updated_decl,
                            struct_layout_map,
                        )
                        if updated_decl != original_decl:
                            replacements.append({"start": start, "end": end, "text": updated_decl})

                    if replacements:
                        replacements.sort(key=lambda item: int(item["start"]), reverse=True)
                        new_content = content
                        for item in replacements:
                            new_content = new_content[: item["start"]] + item["text"] + new_content[item["end"] :]
                        _write_mod_file(source_file, new_content, logger)
                    else:
                        _write_mod_file(source_file, content, logger)
                    result["processed_files"].append(str(source_file))
            except Exception as exc:
                logger.error("Failed processing file: %s", source_file)
                logger.debug(traceback.format_exc())
                result["details"]["errors"].append({"file": str(source_file), "error": str(exc)})

        result["success"] = bool(result["processed_files"] and result["total_variables"] > 0)
        logger.info("carryOverCProcessor complete: success=%s", result["success"])
        return result
    except Exception as exc:
        logger.error("Unhandled error in carryOverCProcessor")
        logger.debug(traceback.format_exc())
        result["details"]["errors"].append({"error": str(exc)})
        return result
