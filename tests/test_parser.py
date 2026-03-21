# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Tests for expression validation and dependency extraction."""

from bexpeng.engine import _extract_dependencies as extract_dependencies
from bexpeng.engine import _validate_expression as validate_expression


class TestValidateExpression:
    def test_valid_simple(self):
        ok, err = validate_expression("2 * x + 1")
        assert ok
        assert err == ""

    def test_valid_function_call(self):
        ok, err = validate_expression("sin(x) + cos(y)")
        assert ok

    def test_invalid_syntax(self):
        ok, err = validate_expression("2 * (")
        assert not ok
        assert err  # non-empty error message

    def test_unary_plus_is_valid(self):
        ok, err = validate_expression("2 * + x")
        assert ok  # unary plus is valid Python

    def test_empty_string(self):
        ok, err = validate_expression("")
        assert not ok


class TestExtractDependencies:
    def test_simple(self):
        known = {"x", "y", "z"}
        deps = extract_dependencies("2 * x + y", known)
        assert deps == {"x", "y"}

    def test_no_spaces(self):
        known = {"a", "b"}
        deps = extract_dependencies("a*b", known)
        assert deps == {"a", "b"}

    def test_function_call_arg(self):
        known = {"length", "width"}
        deps = extract_dependencies("sin(length) + width", known)
        assert deps == {"length", "width"}

    def test_unknown_names_ignored(self):
        known = {"x"}
        deps = extract_dependencies("x + unknown_var", known)
        assert deps == {"x"}

    def test_no_deps(self):
        known = {"x"}
        deps = extract_dependencies("42", known)
        assert deps == set()

    def test_complex_expression(self):
        known = {"wall_thickness_A", "factor"}
        deps = extract_dependencies("wall_thickness_A * factor + 0.01", known)
        assert deps == {"wall_thickness_A", "factor"}

    def test_invalid_expression_returns_empty(self):
        known = {"x"}
        deps = extract_dependencies("2 * (", known)
        assert deps == set()
