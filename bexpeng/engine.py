# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Core parametric engine with dependency graph and expression solver."""

from __future__ import annotations

import ast
from typing import Any, Callable

import networkx as nx
from asteval import Interpreter


def _validate_expression(expression: str) -> tuple[bool, str]:
    """Check if an expression is syntactically valid Python."""
    try:
        ast.parse(expression, mode="eval")
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def _extract_dependencies(expression: str, known_names: set[str]) -> set[str]:
    """Extract parameter names referenced in an expression using the AST."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    deps = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in known_names:
            deps.add(node.id)
    return deps


class CyclicDependencyError(Exception):
    """Raised when registering an expression that would create a cycle."""


class ExpressionSyntaxError(Exception):
    """Raised when an expression string is not valid Python syntax."""


class ParameterStillReferencedError(Exception):
    """Raised when remove_parameter is called while subscribers are still registered."""


class ParameterHasDependentsError(Exception):
    """Raised when remove_parameter is called while other parameters reference this one."""

    def __init__(self, name: str, dependents: list[str]) -> None:
        self.dependents = dependents
        super().__init__(
            f"Cannot remove '{name}': referenced by "
            f"{len(dependents)} parameter(s): {', '.join(dependents)}"
        )


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
        self._subscribers: dict[str, list[Callable[[str], None]]] = {}
        self._ref_counts: dict[str, int] = {}
        self._graph: nx.DiGraph = nx.DiGraph()
        self._aeval: Interpreter = Interpreter()
        self.bexpeng_panel_update: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_parameter(self, name: str, value: Any = None) -> None:
        """Internal: create or update a parameter node."""
        is_new = name not in self._values
        self._values[name] = value
        self._aeval.symtable[name] = value
        if is_new:
            self._graph.add_node(name)
            self._subscribers.setdefault(name, [])

    def _list_parameters(self) -> dict[str, Any]:
        """Internal: return a copy of all parameter names and their current values."""
        return dict(self._values)

    def _list_expressions(self) -> dict[str, str]:
        """Internal: return a copy of all expression definitions."""
        return dict(self._expressions)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def remove_parameter(self, name: str) -> None:
        """Remove a parameter.

        Raises ``ParameterStillReferencedError`` if any subscriber is still registered for *name*.
        Raises ``ParameterHasDependentsError`` if any other parameter's expression references *name*.
        Both guards prevent silent destruction of a parameter other addons or expressions depend on.
        """
        ref = self._ref_counts.get(name, 0)
        if ref > 0:
            raise ParameterStillReferencedError(
                f"Cannot remove '{name}': {ref} subscriber(s) still registered."
            )

        dependents = list(self._graph.successors(name))
        if dependents:
            raise ParameterHasDependentsError(name, dependents)

        self._expressions.pop(name, None)
        self._values.pop(name, None)
        self._aeval.symtable.pop(name, None)
        self._subscribers.pop(name, None)
        self._ref_counts.pop(name, None)
        if self._graph.has_node(name):
            self._graph.remove_node(name)

    def _register_expression(
        self, name: str, expression: str, *, _defer_solve: bool = False
    ) -> None:
        """Internal: validate, cycle-check, and bind an expression to *name*."""
        valid, err = _validate_expression(expression)
        if not valid:
            raise ExpressionSyntaxError(f"Invalid expression for '{name}': {err}")

        if name not in self._values:
            self._register_parameter(name)

        deps = _extract_dependencies(expression, set(self._values.keys()))
        deps.discard(name)

        test_graph = self._graph.copy()
        old_preds = list(test_graph.predecessors(name))
        for pred in old_preds:
            test_graph.remove_edge(pred, name)
        for dep in deps:
            test_graph.add_edge(dep, name)

        if not nx.is_directed_acyclic_graph(test_graph):
            raise CyclicDependencyError(
                f"Expression '{expression}' for '{name}' would create a "
                f"circular dependency."
            )

        old_preds = list(self._graph.predecessors(name))
        for pred in old_preds:
            self._graph.remove_edge(pred, name)
        for dep in deps:
            if not self._graph.has_node(dep):
                self._graph.add_node(dep)
            self._graph.add_edge(dep, name)

        self._expressions[name] = expression
        if not _defer_solve:
            self._solve(name)

    def _unregister_expression(self, name: str) -> None:
        """Internal: remove the expression for a parameter (keeps the parameter)."""
        if name in self._expressions:
            del self._expressions[name]
            preds = list(self._graph.predecessors(name))
            for pred in preds:
                self._graph.remove_edge(pred, name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_parameter(self, name: str, expression: str) -> None:
        """Create or update a parameter with the given expression.

        *expression* can be a literal (``"5.0"``, ``'"hello"'``) or a
        formula referencing other parameters (``"2 * wall_length"``).
        Creates the parameter if it does not exist; updates the expression
        if it does.

        Raises ``ExpressionSyntaxError`` for syntactically invalid expressions and
        ``CyclicDependencyError`` for circular dependencies.
        """
        if name not in self._values:
            self._register_parameter(name)
        self._register_expression(name, expression)

    def get_value(self, name: str) -> Any:
        """Return the current evaluated value, or ``None`` if the parameter is unknown."""
        return self._values.get(name)

    def get_expression(self, name: str) -> str | None:
        """Return the expression string for *name*, or ``None`` if unknown."""
        return self._expressions.get(name)

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------

    def subscribe(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a callback for when a parameter's value changes.

        The callback receives only the parameter name: ``callback(name)``.
        Use ``engine.get_value(name)`` and ``engine.get_expression(name)``
        inside the callback to read the current state.
        Increments the reference count for *name*.
        """
        self._subscribers.setdefault(name, []).append(callback)
        self._ref_counts[name] = self._ref_counts.get(name, 0) + 1

    def unsubscribe(self, name: str, callback: Callable[[str], None]) -> None:
        """Remove a previously registered callback and decrement the reference count."""
        cbs = self._subscribers.get(name, [])
        if callback in cbs:
            cbs.remove(callback)
            self._ref_counts[name] = max(0, self._ref_counts.get(name, 1) - 1)

    def get_ref_count(self, name: str) -> int:
        """Return how many active subscribers (Bonsai bindings) use *name*."""
        return self._ref_counts.get(name, 0)

    def get_dep_count(self, name: str) -> int:
        """Return how many parameters have expressions that reference *name*."""
        if not self._graph.has_node(name):
            return 0
        return len(list(self._graph.successors(name)))

    # ------------------------------------------------------------------
    # Solver (private)
    # ------------------------------------------------------------------

    def _solve(self, root: str | None = None) -> None:
        """Evaluate expressions in topological order.

        If *root* is given, only re-evaluates *root* and its transitive
        dependents (parameters that directly or indirectly depend on *root*).
        If *root* is ``None``, re-evaluates every node that has an expression.
        """
        if root is not None:
            affected = {root} | nx.descendants(self._graph, root)
        else:
            affected = None  # evaluate all
        for node in nx.topological_sort(self._graph):
            if affected is not None and node not in affected:
                continue
            if node not in self._expressions:
                continue
            expr = self._expressions[node]
            # Update interpreter symbol table with latest values
            for dep in self._graph.predecessors(node):
                self._aeval.symtable[dep] = self._values.get(dep)
            try:
                val = self._aeval(expr)
                if self._aeval.error:
                    self._aeval.error = []
                    continue
                old_val = self._values.get(node)
                self._values[node] = val
                self._aeval.symtable[node] = val
                if val != old_val:
                    self._notify(node)
            except Exception:
                pass
        if self.bexpeng_panel_update is not None:
            try:
                self.bexpeng_panel_update()
            except Exception:
                pass

    def _notify(self, name: str) -> None:
        """Call all subscribers for a parameter."""
        for cb in self._subscribers.get(name, []):
            try:
                cb(name)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise engine state to a plain dict (for JSON storage).

        Format: ``{"expressions": {name: expression_str, ...}}``.
        Every parameter is represented by its expression (a literal such as
        ``"5.0"`` for direct values, or a formula like ``"2 * length"``).
        """
        return {"expressions": dict(self._expressions)}

    def load_dict(self, data: dict) -> None:
        """Restore engine state from a dict produced by ``to_dict``."""
        # Suppress the post-solve hook during batch reload; fire once at the end.
        hook = self.bexpeng_panel_update
        self.bexpeng_panel_update = None
        try:
            self.clear()
            expressions = data.get("expressions", {})

            for name in expressions:
                if name not in self._values:
                    self._register_parameter(name)

            for name, expr in expressions.items():
                try:
                    self._register_expression(name, expr, _defer_solve=True)
                except Exception:
                    pass
            self._solve()
        finally:
            self.bexpeng_panel_update = hook
        if hook is not None:
            try:
                hook()
            except Exception:
                pass

    def clear(self) -> None:
        """Remove all parameters, expressions, and subscribers."""
        self._values.clear()
        self._expressions.clear()
        self._subscribers.clear()
        self._graph.clear()
        self._aeval.symtable.clear()
