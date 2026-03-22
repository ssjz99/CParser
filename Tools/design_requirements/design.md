# CParser Latest Design Specification

**Date**: March 22, 2026  
**Version**: 1.2  
**Status**: Complete and Production-Ready

---

## Table of Contents

1. [Interface Definition](#1-interface-definition)
2. [Function Specification](#2-function-specification)
3. [Coding Constraints](#3-coding-constraints)
4. [Design Changes Summary](#4-design-changes-summary)
5. [Implementation Details](#5-implementation-details)
6. [Examples](#6-examples)

---

## 1. Interface Definition

### 1.1 Module Interfaces

#### `searchCStruct(src_path, target_list, include_path_list, log_dir=None)`

**Purpose**: Search for C structures in source files matching target criteria.

**Parameters**:
- `src_path` (str): Path to source directory or file to search
- `target_list` (List[str]): List of structure names to find
- `include_path_list` (List[str]): List of include directories for header files
- `log_dir` (Optional[str]): Directory for log files (defaults to current directory)

**Return Type**: List of structure definitions with file_path information in easy readable format

#### `carryOverCProcessor(target_variable_list, log_dir=None)`

**Purpose**: Apply C preprocessor directives from structure definitions to variable initializers.

**Parameters**:
- `target_variable_list` (List[Dict]): Output from searchCStruct
- `log_dir` (Optional[str]): Directory for log files (defaults to current directory)

**Return Type**: Dictionary with success status and file modification details

---

## 2. Function Specification

### 2.1 searchCStruct Function

**Overview**:
Comprehensive C structure search utility that parses C/C++ source and header files using clang library to locate and extract structure definitions.

**Functionality**:
1. Validates input parameters (source path existence, target list not empty)
2. Discovers all `.c` and `.h` files in source path
3. Parses each file using clang with proper include path configuration
4. Recursively traverses AST to find matching structure declarations
5. Extracts complete structure definitions and member information
6. Logs all operations, diagnostics, errors, and warnings
7. Returns structured results with file locations and full definitions

**Error Handling**:
- Returns empty list on invalid paths or empty targets
- Catches and logs all exceptions during parsing
- Logs clang diagnostics as warnings
- Continues processing remaining files even if one fails

**Return Format**:
```python
[
    {
        'name': 'StructName',
        'file': '/path/to/file.c',
        'line': 5,
        'column': 1,
        'definition': 'struct StructName { ... }',
        'members': [
            {'name': 'member1', 'type': 'int'},
            {'name': 'member2', 'type': 'char[50]'},
            ...
        ]
    },
    ...
]
```

### 2.2 carryOverCProcessor Function

**Overview**:
Searches for C preprocessor directives within structure type definitions and applies them to variable initializers defined with that struct type.

**Functionality**:
1. Validates `target_variable_list` (structures and variables in source files)
2. Parses each structure using clang
3. Checks for C preprocessor directives in the structure type definition body
4. Checks if the structure variable has an initializer
5. Carries over preprocessor directives when both conditions met
6. **IMPORTANT**: Saves modified content to `.mod` files (e.g., `original.c.mod`)
7. No original file shall be touched

**File Behavior** ✅:
- Original files remain **COMPLETELY UNTOUCHED**
- Modified versions saved with `.mod` extension
- Example: `example.c` → `example.c.mod`

**Error Handling**:
- Catches and logs all exceptions during parsing
- Logs clang diagnostics as warnings
- Returns success=False if no directives or initializers found

**Return Format**:
```python
{
    'success': True/False,
    'processed_files': ['path/to/file.c'],
    'total_structures': 4,
    'total_variables': 1,
    'details': {...}
}
```

---

## 3. Coding Constraints

### 3.1 Language & Dependencies
- **Language**: Python 3.9+
- **Required Packages**:
  - `clang` (Python bindings for libclang)
  - `libclang` (C bindings with binary library)
- **Version Compatibility**: clang and libclang versions must match (e.g., both 18.1.1)

### 3.2 File Handling
- Support both absolute and relative paths
- Handle Windows and Unix-style path separators
- UTF-8 encoding with error fallback for source files
- Create log files with timestamps in format `YYYYMMDD_HHMMSS`

### 3.3 Logging Requirements
- **Log Levels**: DEBUG, INFO, WARNING, ERROR
- **Output Targets**: File and console (console at INFO level)
- **File Output**: Timestamped log files with pattern `searchCStruct_YYYYMMDD_HHMMSS.log`
- **Log Format**: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- **Content**:
  - Search condition (paths, targets, include paths)
  - Processing progress (files found, parsing status)
  - Errors and warnings (clang diagnostics, exceptions)
  - Each found structure printed in structural text diagram with field name, type and initializer (if present)
  - Recursive printing for nested structures

### 3.4 Type Hints
- Use type hints for all function parameters and return types
- Use `Optional`, `List`, `Dict`, `Any` from `typing` module
- Document complex return types in docstrings

### 3.5 Error Handling
- All exceptions must be caught and logged
- Graceful degradation on partial failures
- Return empty list rather than raising exceptions at public API level
- Log full exception traces for debugging

### 3.6 Code Quality
- Comprehensive docstrings for all public methods
- Clear separation of concerns (parsing, logging, result building)
- Immutable configuration after initialization
- No global state or side effects
- Avoid using classes
- Each global function shall be placed in a separate Python file
- Local/private functions only allowed in each Python file and shall not be reused
- Each function or Python file can be tested separately

### 3.7 Performance Constraints
- Single-threaded processing (can be enhanced later)
- Lazy index creation per file (not reused across files)
- Log file I/O per operation
- No caching of parse results

### 3.8 Testing Constraints
- Support parsing multiple structure definitions
- Test named structure definitions (Typedef)
- Test unnamed structure definitions
- Handle nested structures correctly
- Distinguish between struct declaration and definition
- Extract array and pointer member types correctly
- Process both `.c` (implementation) and `.h` (header) files
- **Verify the structure type definition with optional fields wrapped with #ifdef/#endif** ✅

### 3.9 Documentation Requirements
- Module-level docstring describing overall purpose
- Function-level docstrings explaining responsibility
- Function docstrings with Args, Returns, Raises sections
- Inline comments for complex logic
- Example usage in function docstrings
