# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Core parametric engine with dependency graph and expression solver."""

from __future__ import annotations

import logging
from typing import Any, Callable

import networkx as nx
from asteval import Interpreter

from . import parser

log = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    """Raised when registering an expression that would create a cycle."""


class ExpressionError(Exception):
    """Raised when an expression fails to evaluate."""


class ParametricEngine:
    """Parametric expression engine.

    Manages named parameters, expressions that compute parameter values
    from other parameters, a dependency graph to determine evaluation
    order, and a subscriber system for change notifications.

    Dependency graph convention:
        An edge ``A -> B`` means "B depends on A", i.e. A must be
        evaluated before B.  ``networkx.topological_sort`` then yields
        A before B, which is the correct evaluation order.
    """

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._expressions: dict[str, str] = {}
        self._subscribers: dict[str, list[Callable[[str, Any], None]]] = {}
        self._ref_counts: dict[str, int] = {}
        self._graph: nx.DiGraph = nx.DiGraph()
        self._aeval: Interpreter = Interpreter()

    # ------------------------------------------------------------------
    # Parameter registration
    # ------------------------------------------------------------------

    def register_parameter(self, name: str, value: Any = None) -> None:
        """Register a named parameter with an optional initial value.

        If the parameter already exists its value is updated.
        """
        is_new = name not in self._values
        self._values[name] = value
        self._aeval.symtable[name] = value
        if is_new:
            self._graph.add_node(name)
            self._subscribers.setdefault(name, [])
            log.debug("Registered parameter '%s' = %r", name, value)

    def unregister_parameter(self, name: str) -> None:
        """Remove a parameter only when no subscribers hold a reference to it.

        If the reference count is still above zero the call is a no-op so that
        renaming one binding does not destroy a parameter still used by others.
        """
        if self._ref_counts.get(name, 0) > 0:
            log.debug(
                "Skipping unregister of '%s': ref_count=%d",
                name,
                self._ref_counts[name],
            )
            return

        # Remove expressions that depend on this parameter
        dependents = list(self._graph.successors(name))
        for dep in dependents:
            self.unregister_expression(dep)

        self._expressions.pop(name, None)
        self._values.pop(name, None)
        self._aeval.symtable.pop(name, None)
        self._subscribers.pop(name, None)
        self._ref_counts.pop(name, None)
        if self._graph.has_node(name):
            self._graph.remove_node(name)
        log.debug("Unregistered parameter '%s'", name)

    # ------------------------------------------------------------------
    # Expression registration
    # ------------------------------------------------------------------

    def register_expression(self, name: str, expression: str) -> None:
        """Bind an expression to a parameter.

        The expression can reference other registered parameters.
        Raises ``CyclicDependencyError`` if this would create a cycle.
        Raises ``SyntaxError`` if the expression is not valid Python.

        Args:
            name: The parameter whose value is computed by the expression.
            expression: A Python expression string (e.g. ``"2 * wall_length"``).
        """
        valid, err = parser.validate_expression(expression)
        if not valid:
            raise SyntaxError(f"Invalid expression for '{name}': {err}")

        # Ensure the target parameter node exists
        if name not in self._values:
            self.register_parameter(name)

        # Determine dependencies
        deps = parser.extract_dependencies(expression, set(self._values.keys()))
        deps.discard(name)  # self-reference would be a cycle, caught below

        # Build a temporary graph to check for cycles
        test_graph = self._graph.copy()
        # Remove old edges pointing into *name*
        old_preds = list(test_graph.predecessors(name))
        for pred in old_preds:
            test_graph.remove_edge(pred, name)
        # Add new edges: dependency -> name
        for dep in deps:
            test_graph.add_edge(dep, name)

        if not nx.is_directed_acyclic_graph(test_graph):
            raise CyclicDependencyError(
                f"Expression '{expression}' for '{name}' would create a "
                f"circular dependency."
            )

        # Commit the graph change
        old_preds = list(self._graph.predecessors(name))
        for pred in old_preds:
            self._graph.remove_edge(pred, name)
        for dep in deps:
            if not self._graph.has_node(dep):
                self._graph.add_node(dep)
            self._graph.add_edge(dep, name)

        self._expressions[name] = expression
        log.debug(
            "Registered expression '%s' = '%s' (deps: %s)", name, expression, deps
        )

        # Evaluate now
        self._solve()

    def unregister_expression(self, name: str) -> None:
        """Remove the expression for a parameter (keeps the parameter)."""
        if name in self._expressions:
            del self._expressions[name]
            # Remove incoming edges (dependencies)
            preds = list(self._graph.predecessors(name))
            for pred in preds:
                self._graph.remove_edge(pred, name)
            log.debug("Unregistered expression for '%s'", name)

    # ------------------------------------------------------------------
    # Value access
    # ------------------------------------------------------------------

    def set_value(self, name: str, value: Any) -> None:
        """Set a parameter value and recompute all dependents."""
        if name not in self._values:
            self.register_parameter(name, value)
        else:
            old_val = self._values[name]
            self._values[name] = value
            self._aeval.symtable[name] = value
            if value != old_val:
                self._notify(name, value)
        self._solve()

    def get_value(self, name: str) -> Any:
        """Return the current value of a parameter, or None if unknown."""
        return self._values.get(name)

    def has_parameter(self, name: str) -> bool:
        return name in self._values

    def has_expression(self, name: str) -> bool:
        return name in self._expressions

    def get_expression(self, name: str) -> str | None:
        return self._expressions.get(name)

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------

    def subscribe(self, name: str, callback: Callable[[str, Any], None]) -> None:
        """Register a callback for when a parameter value changes.

        The callback receives ``(parameter_name, new_value)``.
        Increments the reference count for *name*.
        """
        self._subscribers.setdefault(name, []).append(callback)
        self._ref_counts[name] = self._ref_counts.get(name, 0) + 1

    def unsubscribe(self, name: str, callback: Callable[[str, Any], None]) -> None:
        """Remove a previously registered callback and decrement the reference count."""
        cbs = self._subscribers.get(name, [])
        if callback in cbs:
            cbs.remove(callback)
            self._ref_counts[name] = max(0, self._ref_counts.get(name, 1) - 1)

    def get_ref_count(self, name: str) -> int:
        """Return how many active subscribers (Bonsai bindings) use *name*."""
        return self._ref_counts.get(name, 0)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_parameters(self) -> dict[str, Any]:
        """Return a copy of all parameter names and their current values."""
        return dict(self._values)

    def list_expressions(self) -> dict[str, str]:
        """Return a copy of all expression definitions."""
        return dict(self._expressions)

    def get_dependents(self, name: str) -> list[str]:
        """Return parameters that directly depend on *name*."""
        if not self._graph.has_node(name):
            return []
        return list(self._graph.successors(name))

    def get_dependencies(self, name: str) -> list[str]:
        """Return parameters that *name*'s expression depends on."""
        if not self._graph.has_node(name):
            return []
        return list(self._graph.predecessors(name))

    # ------------------------------------------------------------------
    # Solver (private)
    # ------------------------------------------------------------------

    def _solve(self) -> None:
        """Evaluate all expressions in topological (dependency) order."""
        for node in nx.topological_sort(self._graph):
            if node not in self._expressions:
                continue
            expr = self._expressions[node]
            # Update interpreter symbol table with latest values
            for dep in self._graph.predecessors(node):
                self._aeval.symtable[dep] = self._values.get(dep)
            try:
                val = self._aeval(expr)
                if self._aeval.error:
                    errors = "; ".join(str(e.get_error()[1]) for e in self._aeval.error)
                    log.error("Error evaluating '%s' = '%s': %s", node, expr, errors)
                    self._aeval.error = []
                    continue
                old_val = self._values.get(node)
                self._values[node] = val
                self._aeval.symtable[node] = val
                if val != old_val:
                    self._notify(node, val)
            except Exception as exc:
                log.error("Exception evaluating '%s' = '%s': %s", node, expr, exc)

    def _notify(self, name: str, value: Any) -> None:
        """Call all subscribers for a parameter."""
        for cb in self._subscribers.get(name, []):
            try:
                cb(name, value)
            except Exception as exc:
                log.error("Subscriber error for '%s': %s", name, exc)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise engine state to a plain dict (for JSON storage)."""
        return {
            "parameters": {
                k: v for k, v in self._values.items() if k not in self._expressions
            },
            "expressions": dict(self._expressions),
        }

    def load_dict(self, data: dict) -> None:
        """Restore engine state from a dict produced by ``to_dict``."""
        self.clear()
        for name, value in data.get("parameters", {}).items():
            self.register_parameter(name, value)
        for name, expr in data.get("expressions", {}).items():
            self.register_parameter(name)
            self.register_expression(name, expr)

    def clear(self) -> None:
        """Remove all parameters, expressions, and subscribers."""
        self._values.clear()
        self._expressions.clear()
        self._subscribers.clear()
        self._graph.clear()
        self._aeval.symtable.clear()
