# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Expression parsing and dependency extraction using Python AST."""

import ast


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
