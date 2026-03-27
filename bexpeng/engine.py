# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Core parametric engine with dependency graph and expression solver."""

from __future__ import annotations

import ast
import re
from typing import Any, Callable, ClassVar

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
    """Raised when remove_parameter is called while observers are still attached."""


class ParameterHasDependentsError(Exception):
    """Raised when remove_parameter is called while other parameters reference this one."""

    def __init__(self, name: str, dependents: list[str]) -> None:
        self.dependents = dependents
        super().__init__(
            f"Cannot remove '{name}': referenced by "
            f"{len(dependents)} parameter(s): {', '.join(dependents)}"
        )


class ParameterRenameError(Exception):
    """Raised when rename_parameter fails validation."""


class ExpressionError(Exception):
    """Raised when an expression fails to evaluate."""


class ParametricEngine:
    """Parametric expression engine.

    Manages named parameters, expressions that compute parameter values
    from other parameters, a dependency graph to determine evaluation
    order, and an observer system for change notifications.

    Parameters have two identifiers:

    - **Internal ID** (e.g. ``"bxp1"``): immutable, auto-generated, used as
      the key in all internal dicts, the dependency graph, and the observer
      subscription API (``attach`` / ``detach``).
    - **Name** (e.g. ``"wall_length"``): a mutable Python identifier used in
      expression text and displayed in the UI.  Rename via
      ``rename_parameter``.

    Dependency graph convention:
        An edge ``A -> B`` means "B depends on A", i.e. A must be
        evaluated before B.  ``networkx.topological_sort`` then yields
        A before B, which is the correct evaluation order.
    """

    _instance: ClassVar[ParametricEngine | None] = None

    def __init__(self) -> None:
        self._id_counter: int = 0
        self._ids: dict[str, str] = {}  # pid → name
        self._name_to_id: dict[str, str] = {}  # name → pid
        self._values: dict[str, Any] = {}  # pid → value
        self._expressions: dict[str, str] = {}  # pid → expression string
        self._descriptions: dict[str, str] = {}  # pid → description
        self._observers: dict[str, list[Callable[[str], None]]] = {}  # pid → callbacks
        self._observer_counts: dict[str, int] = {}  # pid → count
        self._graph: nx.DiGraph = nx.DiGraph()  # nodes are pids
        self._aeval: Interpreter = Interpreter()  # symtable keyed by name
        self.ui_observer: Callable[[], None] | None = None
        self._post_load_observers: list[Callable[[], None]] = []
        """Observers fired after every ``load_dict`` call, in registration order.
        Survive ``clear()`` so consumers only need to attach once at addon load."""

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> ParametricEngine:
        """Return the singleton ``ParametricEngine`` instance.

        The instance is created lazily on first call.  All addons share
        the same instance within a Blender session.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Discard the current instance and create a fresh one.

        Primarily used when loading a new ``.blend`` file.  The
        ``ui_observer`` registered by the UI layer is preserved on the
        replacement instance.
        """
        old = cls._instance
        hook = old.ui_observer if old is not None else None
        if old is not None:
            old.clear()
        cls._instance = cls()
        cls._instance.ui_observer = hook

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        """Return the next unused internal parameter ID."""
        pid = f"bxp{self._id_counter}"
        self._id_counter += 1
        return pid

    def _register_parameter(self, pid: str, name: str, value: Any = None) -> None:
        """Internal: initialise storage for a new parameter keyed by *pid*."""
        self._values[pid] = value
        self._aeval.symtable[name] = value
        self._graph.add_node(pid)
        self._observers.setdefault(pid, [])

    def _list_parameters(self) -> dict[str, Any]:
        """Internal: return ``{name: value}`` for all parameters."""
        return {self._ids[pid]: v for pid, v in self._values.items()}

    def _list_expressions(self) -> dict[str, str]:
        """Internal: return ``{name: expression}`` for all parameters."""
        return {self._ids[pid]: e for pid, e in self._expressions.items()}

    def _list_descriptions(self) -> dict[str, str]:
        """Internal: return ``{name: description}`` for all parameters."""
        return {self._ids[pid]: d for pid, d in self._descriptions.items()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_parameters(self) -> list[dict]:
        """Return a list of dicts describing all registered parameters.

        Each dict has keys: ``"id"``, ``"name"``, ``"value"``,
        ``"expression"``, ``"description"``.  The ``"id"`` value is the
        stable internal ID to pass to ``attach`` / ``detach``.
        """
        return [
            {
                "id": pid,
                "name": self._ids[pid],
                "value": self._values.get(pid),
                "expression": self._expressions.get(pid, "0"),
                "description": self._descriptions.get(pid, ""),
            }
            for pid in self._ids
        ]

    def get_id(self, name: str) -> str | None:
        """Return the internal ID for the parameter named *name*, or ``None``."""
        return self._name_to_id.get(name)

    def remove_parameter(self, name: str) -> None:
        """Remove a parameter.

        Raises ``ParameterStillReferencedError`` if any observer is still attached for *name*.
        Raises ``ParameterHasDependentsError`` if any other parameter's expression references *name*.
        Both guards prevent silent destruction of a parameter other addons or expressions depend on.
        """
        pid = self._name_to_id.get(name)
        if pid is None:
            return

        ref = self._observer_counts.get(pid, 0)
        if ref > 0:
            raise ParameterStillReferencedError(
                f"Cannot remove '{name}': {ref} observer(s) still attached."
            )

        dependent_pids = list(self._graph.successors(pid))
        if dependent_pids:
            dependent_names = [self._ids[d] for d in dependent_pids]
            raise ParameterHasDependentsError(name, dependent_names)

        self._expressions.pop(pid, None)
        self._descriptions.pop(pid, None)
        self._values.pop(pid, None)
        self._aeval.symtable.pop(name, None)
        self._observers.pop(pid, None)
        self._observer_counts.pop(pid, None)
        if self._graph.has_node(pid):
            self._graph.remove_node(pid)
        self._ids.pop(pid, None)
        self._name_to_id.pop(name, None)

    def rename_parameter(self, old_name: str, new_name: str) -> None:
        """Rename a parameter from *old_name* to *new_name*.

        Rewrites all expressions that reference *old_name* using
        word-boundary-safe substitution so partial identifiers are never
        clobbered.  Observers are keyed by internal ID and are completely
        unaffected — they continue to fire; callbacks now receive *new_name*.

        Raises ``ParameterRenameError`` if *new_name* is not a valid Python
        identifier or is already in use, or if *old_name* does not exist.
        """
        if not new_name.isidentifier():
            raise ParameterRenameError(f"'{new_name}' is not a valid Python identifier")
        if new_name in self._name_to_id:
            raise ParameterRenameError(f"Parameter '{new_name}' already exists")
        if old_name not in self._name_to_id:
            raise ParameterRenameError(f"Parameter '{old_name}' does not exist")

        pid = self._name_to_id[old_name]
        pattern = re.compile(r"\b" + re.escape(old_name) + r"\b")
        for epid in list(self._expressions):
            rewritten = pattern.sub(new_name, self._expressions[epid])
            if rewritten != self._expressions[epid]:
                self._expressions[epid] = rewritten

        self._ids[pid] = new_name
        del self._name_to_id[old_name]
        self._name_to_id[new_name] = pid

        val = self._aeval.symtable.pop(old_name, None)
        self._aeval.symtable[new_name] = val

        self._solve(pid)

    def _register_expression(
        self, pid: str, expression: str, *, _defer_solve: bool = False
    ) -> None:
        """Internal: validate, cycle-check, and bind an expression to *pid*."""
        name = self._ids[pid]
        valid, err = _validate_expression(expression)
        if not valid:
            raise ExpressionSyntaxError(f"Invalid expression for '{name}': {err}")

        known_names = set(self._name_to_id.keys())
        dep_names = _extract_dependencies(expression, known_names)
        dep_names.discard(name)
        dep_ids = {self._name_to_id[n] for n in dep_names}

        test_graph = self._graph.copy()
        for pred in list(test_graph.predecessors(pid)):
            test_graph.remove_edge(pred, pid)
        for dep_pid in dep_ids:
            test_graph.add_edge(dep_pid, pid)

        if not nx.is_directed_acyclic_graph(test_graph):
            raise CyclicDependencyError(
                f"Expression '{expression}' for '{name}' would create a "
                f"circular dependency."
            )

        for pred in list(self._graph.predecessors(pid)):
            self._graph.remove_edge(pred, pid)
        for dep_pid in dep_ids:
            self._graph.add_edge(dep_pid, pid)

        self._expressions[pid] = expression
        if not _defer_solve:
            self._solve(pid)

    def _unregister_expression(self, pid: str) -> None:
        """Internal: remove the expression for *pid* (keeps the parameter)."""
        if pid in self._expressions:
            del self._expressions[pid]
            for pred in list(self._graph.predecessors(pid)):
                self._graph.remove_edge(pred, pid)

    # ------------------------------------------------------------------
    # Public API (continued)
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
        if name not in self._name_to_id:
            pid = self._generate_id()
            self._ids[pid] = name
            self._name_to_id[name] = pid
            self._register_parameter(pid, name)
        else:
            pid = self._name_to_id[name]
        self._register_expression(pid, expression)

    def get_value(self, name: str) -> Any:
        """Return the current evaluated value, or ``None`` if the parameter is unknown."""
        pid = self._name_to_id.get(name)
        return self._values.get(pid) if pid is not None else None

    def get_expression(self, name: str) -> str | None:
        """Return the expression string for *name*, or ``None`` if unknown."""
        pid = self._name_to_id.get(name)
        return self._expressions.get(pid) if pid is not None else None

    def set_description(self, name: str, description: str) -> None:
        """Set a human-readable description for *name*. No-op if the parameter does not exist."""
        pid = self._name_to_id.get(name)
        if pid is not None:
            self._descriptions[pid] = description

    def get_description(self, name: str) -> str:
        """Return the description for *name*, or an empty string if unset."""
        pid = self._name_to_id.get(name)
        return self._descriptions.get(pid, "") if pid is not None else ""

    # ------------------------------------------------------------------
    # Observers — keyed by internal ID
    # ------------------------------------------------------------------

    def attach(self, pid: str, callback: Callable[[str], None]) -> None:
        """Attach an observer for when a parameter's value changes.

        *pid* must be the **internal ID** returned by ``get_id(name)`` or
        ``list_parameters()``.  The callback receives the parameter's current
        *name* as its sole argument: ``callback(name)``.

        Increments the observer count for *pid*.
        """
        self._observers.setdefault(pid, []).append(callback)
        self._observer_counts[pid] = self._observer_counts.get(pid, 0) + 1

    def detach(self, pid: str, callback: Callable[[str], None]) -> None:
        """Detach a previously attached observer and decrement the observer count."""
        cbs = self._observers.get(pid, [])
        if callback in cbs:
            cbs.remove(callback)
            self._observer_counts[pid] = max(0, self._observer_counts.get(pid, 1) - 1)

    def get_observer_count(self, name: str) -> int:
        """Return how many observers are currently attached to *name*."""
        pid = self._name_to_id.get(name)
        return self._observer_counts.get(pid, 0) if pid is not None else 0

    def get_dep_count(self, name: str) -> int:
        """Return how many parameters have expressions that reference *name*."""
        pid = self._name_to_id.get(name)
        if pid is None or not self._graph.has_node(pid):
            return 0
        return len(list(self._graph.successors(pid)))

    # ------------------------------------------------------------------
    # Solver (private)
    # ------------------------------------------------------------------

    def _solve(self, root: str | None = None) -> None:
        """Evaluate expressions in topological order.

        *root* is an internal ID.  If given, only re-evaluates *root* and its
        transitive dependents.  If ``None``, re-evaluates every node that has
        an expression.
        """
        if root is not None:
            affected = {root} | nx.descendants(self._graph, root)
        else:
            affected = None  # evaluate all
        for node_pid in nx.topological_sort(self._graph):
            if affected is not None and node_pid not in affected:
                continue
            if node_pid not in self._expressions:
                continue
            expr = self._expressions[node_pid]
            for dep_pid in self._graph.predecessors(node_pid):
                dep_name = self._ids[dep_pid]
                self._aeval.symtable[dep_name] = self._values.get(dep_pid)
            try:
                val = self._aeval(expr)
                if self._aeval.error:
                    self._aeval.error = []
                    continue
                old_val = self._values.get(node_pid)
                self._values[node_pid] = val
                node_name = self._ids[node_pid]
                self._aeval.symtable[node_name] = val
                if val != old_val:
                    self.notify(node_pid)
            except Exception:
                pass
        if self.ui_observer is not None:
            try:
                self.ui_observer()
            except Exception:
                pass

    def notify(self, pid: str) -> None:
        """Call all attached observers for the parameter identified by *pid*."""
        name = self._ids.get(pid, pid)
        callbacks = list(self._observers.get(pid, []))  # copy: safe against mutation
        for cb in callbacks:
            try:
                cb(name)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise engine state to a plain dict (for JSON storage).

        Format includes ``"ids"`` (pid→name map) and ``"id_counter"`` so that
        internal IDs are stable across save/load cycles.
        """
        return {
            "ids": dict(self._ids),
            "id_counter": self._id_counter,
            "expressions": {
                self._ids[pid]: expr for pid, expr in self._expressions.items()
            },
            "descriptions": {
                self._ids[pid]: desc for pid, desc in self._descriptions.items()
            },
        }

    def load_dict(self, data: dict) -> None:
        """Restore engine state from a dict produced by ``to_dict``.

        Handles both the current format (with ``"ids"`` / ``"id_counter"``)
        and the legacy format (expressions keyed by name only) so that old
        ``.blend`` files load correctly.

        After ``_solve()`` completes, all ``_post_load_observers`` are notified
        in registration order so that consumers can re-attach deterministically.
        """
        # Suppress ui_observer during batch reload; fire once at the end.
        hook = self.ui_observer
        self.ui_observer = None
        try:
            self.clear()
            if "ids" in data:
                # Current format: restore stable IDs and counter.
                self._id_counter = data.get("id_counter", 0)
                for pid, name in data["ids"].items():
                    self._ids[pid] = name
                    self._name_to_id[name] = pid
                    self._register_parameter(pid, name)
            else:
                # Legacy format: generate fresh IDs from expression names.
                for name in data.get("expressions", {}):
                    if name not in self._name_to_id:
                        pid = self._generate_id()
                        self._ids[pid] = name
                        self._name_to_id[name] = pid
                        self._register_parameter(pid, name)

            for name, expr in data.get("expressions", {}).items():
                pid = self._name_to_id.get(name)
                if pid:
                    try:
                        self._register_expression(pid, expr, _defer_solve=True)
                    except Exception:
                        pass
            for name, desc in data.get("descriptions", {}).items():
                self.set_description(name, desc)
            self._solve()
        finally:
            self.ui_observer = hook
        if hook is not None:
            try:
                hook()
            except Exception:
                pass
        for cb in list(self._post_load_observers):
            try:
                cb()
            except Exception:
                pass

    def attach_post_load(self, cb: Callable[[], None]) -> None:
        """Attach *cb* as an observer called after each ``load_dict`` call completes.

        Idempotent: attaching the same callable twice has no effect.
        Post-load observers survive ``clear()`` so consumers attach once at
        addon load time and are automatically notified on every file reload.
        """
        if cb not in self._post_load_observers:
            self._post_load_observers.append(cb)

    def detach_post_load(self, cb: Callable[[], None]) -> None:
        """Detach a previously attached post-load observer."""
        self._post_load_observers = [
            c for c in self._post_load_observers if c is not cb
        ]

    def clear(self) -> None:
        """Remove all parameters, expressions, and attached observers.

        ``_post_load_observers`` are intentionally preserved — they are
        consumer-registered hooks that must survive reloads.
        """
        self._id_counter = 0
        self._ids.clear()
        self._name_to_id.clear()
        self._values.clear()
        self._expressions.clear()
        self._descriptions.clear()
        self._observers.clear()
        self._observer_counts.clear()
        self._graph.clear()
        self._aeval.symtable.clear()
