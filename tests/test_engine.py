# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Tests for the parametric engine core — exercises the public API only."""

import pytest
from bexpeng.engine import (
    CyclicDependencyError,
    ExpressionSyntaxError,
    ParameterHasDependentsError,
    ParameterRenameError,
    ParameterStillReferencedError,
    ParametricEngine,
)


class TestParameters:
    def test_set_and_get_numeric(self):
        e = ParametricEngine()
        e.set_parameter("x", "5")
        assert e.get_value("x") == pytest.approx(5.0)

    def test_set_and_get_string(self):
        e = ParametricEngine()
        e.set_parameter("label", '"hello"')
        assert e.get_value("label") == "hello"

    def test_get_expression(self):
        e = ParametricEngine()
        e.set_parameter("x", "3 + 2")
        assert e.get_expression("x") == "3 + 2"

    def test_unknown_parameter_returns_none(self):
        e = ParametricEngine()
        assert e.get_value("missing") is None
        assert e.get_expression("missing") is None

    def test_unregister(self):
        e = ParametricEngine()
        e.set_parameter("x", "5")
        e.remove_parameter("x")
        assert e.get_value("x") is None

    def test_unregister_raises_if_subscribed(self):
        e = ParametricEngine()
        e.set_parameter("x", "5")
        e.attach(e.get_id("x"), lambda n: None)
        with pytest.raises(ParameterStillReferencedError):
            e.remove_parameter("x")

    def test_unregister_raises_if_has_dependents(self):
        e = ParametricEngine()
        e.set_parameter("x", "5")
        e.set_parameter("y", "x + 1")
        with pytest.raises(ParameterHasDependentsError) as exc_info:
            e.remove_parameter("x")
        assert "y" in exc_info.value.dependents

    def test_unregister_raises_subscribed_before_dependents(self):
        e = ParametricEngine()
        e.set_parameter("x", "5")
        e.set_parameter("y", "x + 1")
        e.attach(e.get_id("x"), lambda n: None)
        # subscriber check runs first
        with pytest.raises(ParameterStillReferencedError):
            e.remove_parameter("x")


class TestExpressions:
    def test_formula_computes_value(self):
        e = ParametricEngine()
        e.set_parameter("a", "3")
        e.set_parameter("b", "a * 2")
        assert e.get_value("b") == 6

    def test_multiple_deps(self):
        e = ParametricEngine()
        e.set_parameter("x", "2")
        e.set_parameter("y", "3")
        e.set_parameter("z", "x + y")
        assert e.get_value("z") == 5

    def test_chained(self):
        e = ParametricEngine()
        e.set_parameter("a", "5")
        e.set_parameter("b", "a * 2")
        e.set_parameter("c", "b + 1")
        assert e.get_value("b") == 10
        assert e.get_value("c") == 11

    def test_update_source_recomputes_dependents(self):
        e = ParametricEngine()
        e.set_parameter("line_length", "5")
        e.set_parameter("wall_length", "2 * line_length")
        assert e.get_value("wall_length") == 10
        e.set_parameter("line_length", "7")
        assert e.get_value("wall_length") == 14

    def test_no_spaces_formula(self):
        e = ParametricEngine()
        e.set_parameter("a", "4")
        e.set_parameter("b", "a*3")
        assert e.get_value("b") == 12

    def test_update_expression(self):
        e = ParametricEngine()
        e.set_parameter("x", "2")
        e.set_parameter("y", "x + 1")
        assert e.get_value("y") == 3
        e.set_parameter("y", "x * 10")
        assert e.get_value("y") == 20

    def test_invalid_expression_raises(self):
        e = ParametricEngine()
        with pytest.raises(ExpressionSyntaxError):
            e.set_parameter("y", "2 * (")

    def test_string_literal(self):
        e = ParametricEngine()
        e.set_parameter("label", '"A-01"')
        assert e.get_value("label") == "A-01"

    def test_string_concat(self):
        e = ParametricEngine()
        e.set_parameter("prefix", '"Wall-"')
        e.set_parameter("name", "prefix + 'A'")
        assert e.get_value("name") == "Wall-A"

    def test_fstring(self):
        e = ParametricEngine()
        e.set_parameter("floor", "3")
        e.set_parameter("label", 'f"Level {floor}"')
        assert e.get_value("label") == "Level 3"

    def test_fstring_updates_on_dependency_change(self):
        e = ParametricEngine()
        e.set_parameter("storey", "1")
        e.set_parameter("label", 'f"S{storey:02d}"')
        assert e.get_value("label") == "S01"
        e.set_parameter("storey", "5")
        assert e.get_value("label") == "S05"


class TestCycleDetection:
    def test_direct_cycle(self):
        e = ParametricEngine()
        e.set_parameter("a", "1")
        e.set_parameter("b", "a + 1")
        with pytest.raises(CyclicDependencyError):
            e.set_parameter("a", "b + 1")

    def test_indirect_cycle(self):
        e = ParametricEngine()
        e.set_parameter("a", "1")
        e.set_parameter("b", "a + 1")
        e.set_parameter("c", "b + 1")
        with pytest.raises(CyclicDependencyError):
            e.set_parameter("a", "c + 1")


class TestIDs:
    def test_get_id_returns_string(self):
        e = ParametricEngine()
        e.set_parameter("x", "1")
        pid = e.get_id("x")
        assert isinstance(pid, str)
        assert pid.startswith("bxp")

    def test_get_id_unknown_returns_none(self):
        e = ParametricEngine()
        assert e.get_id("missing") is None

    def test_ids_are_unique(self):
        e = ParametricEngine()
        e.set_parameter("a", "1")
        e.set_parameter("b", "2")
        assert e.get_id("a") != e.get_id("b")

    def test_list_parameters_keys(self):
        e = ParametricEngine()
        e.set_parameter("x", "5")
        params = e.list_parameters()
        assert len(params) == 1
        p = params[0]
        assert set(p.keys()) >= {"id", "name", "value", "expression", "description"}
        assert p["name"] == "x"
        assert p["id"] == e.get_id("x")
        assert p["value"] == pytest.approx(5.0)


class TestRename:
    def test_rename_basic(self):
        e = ParametricEngine()
        e.set_parameter("a", "1.0")
        e.rename_parameter("a", "c")
        assert e.get_value("c") == pytest.approx(1.0)
        assert e.get_value("a") is None

    def test_rename_rewrites_dependent_expressions(self):
        e = ParametricEngine()
        e.set_parameter("a", "1.0")
        e.set_parameter("b", "a + 2")
        e.rename_parameter("a", "c")
        assert e.get_expression("b") == "c + 2"
        assert e.get_value("b") == pytest.approx(3.0)

    def test_rename_does_not_clobber_partial_names(self):
        e = ParametricEngine()
        e.set_parameter("ar", "1.0")
        e.set_parameter("area", "2.0")
        e.set_parameter("total", "ar + area")
        e.rename_parameter("ar", "radius")
        assert e.get_expression("total") == "radius + area"

    def test_rename_preserves_internal_id(self):
        e = ParametricEngine()
        e.set_parameter("a", "1.0")
        pid_before = e.get_id("a")
        e.rename_parameter("a", "c")
        assert e.get_id("c") == pid_before

    def test_rename_observer_survives(self):
        e = ParametricEngine()
        e.set_parameter("a", "1.0")
        pid = e.get_id("a")
        received = []
        e.attach(pid, lambda name: received.append(name))
        e.rename_parameter("a", "c")
        e.set_parameter("c", "2.0")  # triggers observer
        assert "c" in received

    def test_rename_error_duplicate(self):
        e = ParametricEngine()
        e.set_parameter("a", "1")
        e.set_parameter("b", "2")
        with pytest.raises(ParameterRenameError):
            e.rename_parameter("a", "b")

    def test_rename_error_invalid_identifier(self):
        e = ParametricEngine()
        e.set_parameter("a", "1")
        with pytest.raises(ParameterRenameError):
            e.rename_parameter("a", "not-valid")

    def test_rename_error_unknown(self):
        e = ParametricEngine()
        with pytest.raises(ParameterRenameError):
            e.rename_parameter("missing", "x")


class TestSubscribers:
    def test_callback_on_change(self):
        e = ParametricEngine()
        e.set_parameter("x", "1")
        e.set_parameter("y", "x * 2")
        updates = []
        e.attach(e.get_id("y"), lambda name: updates.append((name, e.get_value(name))))
        e.set_parameter("x", "5")
        assert ("y", 10) in updates

    def test_unsubscribe(self):
        e = ParametricEngine()
        e.set_parameter("x", "1")
        calls = []
        cb = lambda name: calls.append(e.get_value(name))
        pid = e.get_id("x")
        e.attach(pid, cb)
        e.set_parameter("x", "2")
        assert len(calls) == 1
        e.detach(pid, cb)
        e.set_parameter("x", "3")
        assert len(calls) == 1  # not called again

    def test_ref_count(self):
        e = ParametricEngine()
        e.set_parameter("x", "1")
        assert e.get_observer_count("x") == 0
        cb = lambda n: None
        pid = e.get_id("x")
        e.attach(pid, cb)
        assert e.get_observer_count("x") == 1
        e.detach(pid, cb)
        assert e.get_observer_count("x") == 0


class TestSerialization:
    def test_round_trip(self):
        e = ParametricEngine()
        e.set_parameter("line_length", "5")
        e.set_parameter("wall_length", "2 * line_length")
        data = e.to_dict()
        e2 = ParametricEngine()
        e2.load_dict(data)
        assert e2.get_value("line_length") == 5

    def test_round_trip_preserves_ids(self):
        e = ParametricEngine()
        e.set_parameter("x", "1")
        pid = e.get_id("x")
        data = e.to_dict()
        e2 = ParametricEngine()
        e2.load_dict(data)
        assert e2.get_id("x") == pid

    def test_legacy_format_loads(self):
        """Old .blend files without 'ids' key should load without error."""
        legacy = {
            "expressions": {"x": "5", "y": "x + 1"},
            "descriptions": {},
        }
        e = ParametricEngine()
        e.load_dict(legacy)
        assert e.get_value("x") == pytest.approx(5.0)
        assert e.get_value("y") == pytest.approx(6.0)
        assert e.get_id("x") is not None

    def test_clear(self):
        e = ParametricEngine()
        e.set_parameter("x", "1")
        e.clear()
        assert e.get_value("x") is None
