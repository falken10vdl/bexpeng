# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Tests for the parametric engine core."""

import pytest
from bexpeng.engine import CyclicDependencyError, ParametricEngine


class TestParameterRegistration:
    def test_register_and_get(self):
        e = ParametricEngine()
        e.register_parameter("x", 5)
        assert e.get_value("x") == 5

    def test_register_without_value(self):
        e = ParametricEngine()
        e.register_parameter("x")
        assert e.get_value("x") is None

    def test_has_parameter(self):
        e = ParametricEngine()
        assert not e.has_parameter("x")
        e.register_parameter("x", 1)
        assert e.has_parameter("x")

    def test_unregister(self):
        e = ParametricEngine()
        e.register_parameter("x", 5)
        e.unregister_parameter("x")
        assert not e.has_parameter("x")

    def test_set_value_auto_registers(self):
        e = ParametricEngine()
        e.set_value("x", 10)
        assert e.get_value("x") == 10
        assert e.has_parameter("x")


class TestExpressions:
    def test_simple_expression(self):
        e = ParametricEngine()
        e.register_parameter("a", 3)
        e.register_parameter("b")
        e.register_expression("b", "a * 2")
        assert e.get_value("b") == 6

    def test_expression_with_multiple_deps(self):
        e = ParametricEngine()
        e.register_parameter("x", 2)
        e.register_parameter("y", 3)
        e.register_parameter("z")
        e.register_expression("z", "x + y")
        assert e.get_value("z") == 5

    def test_chained_expressions(self):
        e = ParametricEngine()
        e.register_parameter("a", 5)
        e.register_parameter("b")
        e.register_parameter("c")
        e.register_expression("b", "a * 2")  # b = 10
        e.register_expression("c", "b + 1")  # c = 11
        assert e.get_value("b") == 10
        assert e.get_value("c") == 11

    def test_set_value_recomputes(self):
        e = ParametricEngine()
        e.register_parameter("line_length", 5)
        e.register_parameter("wall_length")
        e.register_expression("wall_length", "2 * line_length")
        assert e.get_value("wall_length") == 10

        e.set_value("line_length", 7)
        assert e.get_value("wall_length") == 14

    def test_no_spaces_expression(self):
        e = ParametricEngine()
        e.register_parameter("a", 4)
        e.register_parameter("b")
        e.register_expression("b", "a*3")
        assert e.get_value("b") == 12

    def test_update_expression(self):
        e = ParametricEngine()
        e.register_parameter("x", 2)
        e.register_parameter("y")
        e.register_expression("y", "x + 1")
        assert e.get_value("y") == 3
        e.register_expression("y", "x * 10")
        assert e.get_value("y") == 20

    def test_unregister_expression(self):
        e = ParametricEngine()
        e.register_parameter("x", 5)
        e.register_parameter("y")
        e.register_expression("y", "x + 1")
        e.unregister_expression("y")
        assert not e.has_expression("y")
        # y still exists as a parameter
        assert e.has_parameter("y")

    def test_invalid_expression_raises(self):
        e = ParametricEngine()
        e.register_parameter("x", 1)
        with pytest.raises(SyntaxError):
            e.register_expression("y", "2 * (")

    def test_string_expression_literal(self):
        e = ParametricEngine()
        e.register_parameter("label")
        e.register_expression("label", '"A-01"')
        assert e.get_value("label") == "A-01"

    def test_string_expression_concat(self):
        e = ParametricEngine()
        e.register_parameter("prefix", "Wall-")
        e.register_parameter("name")
        e.register_expression("name", "prefix + 'A'")
        assert e.get_value("name") == "Wall-A"

    def test_fstring_number_in_string(self):
        e = ParametricEngine()
        e.register_parameter("floor", 3)
        e.register_parameter("label")
        e.register_expression("label", 'f"Level {floor}"')
        assert e.get_value("label") == "Level 3"

    def test_fstring_string_and_number(self):
        e = ParametricEngine()
        e.register_parameter("base", "Wall")
        e.register_parameter("n", 42)
        e.register_parameter("tag")
        e.register_expression("tag", 'f"{base}_{n}"')
        assert e.get_value("tag") == "Wall_42"

    def test_fstring_updates_on_dependency_change(self):
        e = ParametricEngine()
        e.register_parameter("storey", 1)
        e.register_parameter("label")
        e.register_expression("label", 'f"S{storey:02d}"')
        assert e.get_value("label") == "S01"
        e.set_value("storey", 5)
        assert e.get_value("label") == "S05"


class TestCycleDetection:
    def test_direct_cycle(self):
        e = ParametricEngine()
        e.register_parameter("a", 1)
        e.register_parameter("b")
        e.register_expression("b", "a + 1")
        with pytest.raises(CyclicDependencyError):
            e.register_expression("a", "b + 1")

    def test_indirect_cycle(self):
        e = ParametricEngine()
        e.register_parameter("a", 1)
        e.register_parameter("b")
        e.register_parameter("c")
        e.register_expression("b", "a + 1")
        e.register_expression("c", "b + 1")
        with pytest.raises(CyclicDependencyError):
            e.register_expression("a", "c + 1")


class TestSubscribers:
    def test_subscriber_called_on_change(self):
        e = ParametricEngine()
        e.register_parameter("x", 1)
        e.register_parameter("y")
        e.register_expression("y", "x * 2")

        updates = []
        e.subscribe("y", lambda name, val: updates.append((name, val)))

        e.set_value("x", 5)
        assert ("y", 10) in updates

    def test_unsubscribe(self):
        e = ParametricEngine()
        e.register_parameter("x", 1)

        calls = []
        cb = lambda name, val: calls.append(val)
        e.subscribe("x", cb)
        e.set_value("x", 2)
        assert len(calls) == 1

        e.unsubscribe("x", cb)
        e.set_value("x", 3)
        assert len(calls) == 1  # not called again


class TestIntrospection:
    def test_list_parameters(self):
        e = ParametricEngine()
        e.register_parameter("a", 1)
        e.register_parameter("b", 2)
        assert e.list_parameters() == {"a": 1, "b": 2}

    def test_get_dependents(self):
        e = ParametricEngine()
        e.register_parameter("x", 1)
        e.register_parameter("y")
        e.register_expression("y", "x + 1")
        assert "y" in e.get_dependents("x")

    def test_get_dependencies(self):
        e = ParametricEngine()
        e.register_parameter("x", 1)
        e.register_parameter("y")
        e.register_expression("y", "x + 1")
        assert "x" in e.get_dependencies("y")


class TestSerialization:
    def test_round_trip(self):
        e = ParametricEngine()
        e.register_parameter("line_length", 5)
        e.register_parameter("wall_length")
        e.register_expression("wall_length", "2 * line_length")

        data = e.to_dict()
        e2 = ParametricEngine()
        e2.load_dict(data)

        assert e2.get_value("line_length") == 5
        assert e2.get_value("wall_length") == 10
        assert e2.get_expression("wall_length") == "2 * line_length"

    def test_clear(self):
        e = ParametricEngine()
        e.register_parameter("x", 1)
        e.clear()
        assert not e.has_parameter("x")
        assert e.list_parameters() == {}
