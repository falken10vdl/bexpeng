# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Tests for the expression parser."""

import pytest
from bexpeng.parser import (
    extract_dependencies,
    format_direct_value,
    parse_manual_value,
    validate_expression,
)


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


class TestParseManualValue:
    def test_numeric_value(self):
        ok, value, err = parse_manual_value("12.5")
        assert ok
        assert value == pytest.approx(12.5)
        assert err == ""

    def test_empty_defaults_to_zero(self):
        ok, value, err = parse_manual_value("   ")
        assert ok
        assert value == 0.0
        assert err == ""

    def test_quoted_string_literal(self):
        ok, value, err = parse_manual_value('"hello"')
        assert ok
        assert value == "hello"
        assert err == ""

    def test_unquoted_string_is_rejected(self):
        ok, value, err = parse_manual_value("hello")
        assert not ok
        assert value is None
        assert "quoted string literal" in err

    def test_non_string_python_literal_is_rejected(self):
        ok, value, err = parse_manual_value("[1, 2]")
        assert not ok
        assert value is None
        assert "Only numbers and quoted string literals" in err


class TestFormatDirectValue:
    def test_string_uses_double_quotes(self):
        assert format_direct_value("Hola") == '"Hola"'

    def test_number_uses_plain_str(self):
        assert format_direct_value(3.14) == "3.14"

    def test_round_trips_through_parse(self):
        # Whatever format_direct_value produces must be accepted by parse_manual_value
        for v in ("hello", "Wall-A", 'say "hi"'):
            formatted = format_direct_value(v)
            ok, parsed, _ = parse_manual_value(formatted)
            assert ok and parsed == v
