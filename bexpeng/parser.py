# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Expression parsing and dependency extraction using Python AST."""

import ast
import json


def extract_dependencies(expression: str, known_names: set[str]) -> set[str]:
    """Extract parameter names referenced in an expression.

    Uses Python's AST to find all Name nodes that match known parameter names.
    This correctly handles expressions like '2*x', 'sin(x)+y', 'a*(b+c)', etc.

    Args:
        expression: The expression string to parse.
        known_names: Set of currently registered parameter names.

    Returns:
        Set of parameter names that the expression depends on.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()

    deps = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in known_names:
            deps.add(node.id)
    return deps


def validate_expression(expression: str) -> tuple[bool, str]:
    """Check if an expression is syntactically valid Python.

    Args:
        expression: The expression string to validate.

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    try:
        ast.parse(expression, mode="eval")
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def parse_manual_value(value_text: str) -> tuple[bool, object, str]:
    """Parse a non-expression value entered in the UI.

    Rules:
    - Empty text resolves to ``0.0`` for backward compatibility.
    - Unquoted numerics are accepted (e.g. ``42``, ``3.14``).
    - Quoted Python string literals are accepted
      (e.g. ``"wall"``, ``'A-01'``).

    Args:
        value_text: Raw text from the value field (without a leading ``=``).

    Returns:
        Tuple ``(ok, value, error_message)``.
    """
    text = value_text.strip()
    if not text:
        return True, 0.0, ""

    # Keep legacy behavior for plain numbers entered without quotes.
    try:
        return True, float(text), ""
    except ValueError:
        pass

    # Accept string literals exactly as Python/asteval would parse them.
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return (
            False,
            None,
            "Value must be a number, a quoted string literal, or start with '=' for an expression",
        )

    if isinstance(parsed, str):
        return True, parsed, ""

    return (
        False,
        None,
        "Only numbers and quoted string literals are allowed for direct values",
    )


def format_direct_value(value: object) -> str:
    """Format a direct parameter value for storage in the raw_value UI field.

    String values are wrapped in double quotes so the UI clearly distinguishes
    them from numbers and they round-trip correctly via parse_manual_value.
    Numbers and other types use plain str().
    """
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
