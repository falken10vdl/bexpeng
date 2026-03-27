# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Group manager for bexpeng — organises parameters into a collapsible tree.

Pure-Python module; no Blender dependency so it is fully unit-testable.
"""

from __future__ import annotations

ROOT_GROUP_ID = "bxpg_root"
"""Immutable ID of the permanent root group.  Always present; cannot be removed."""


class GroupManager:
    """Manages named groups that organise parameters.

    Groups form an arbitrary-depth tree.  Membership is many-to-many:
    a parameter can belong to multiple groups.

    Use ``GroupManager.get_instance()`` to obtain the process-wide singleton.
    """

    _instance: "GroupManager | None" = None

    # ─── Singleton ────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "GroupManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._id_counter: int = 0
        # group_id → {"name": str, "parent_id": str}
        self._groups: dict = {}
        # group_id → set[param_id]
        self._memberships: dict = {}
        self._ensure_root()

    def _ensure_root(self) -> None:
        """Create the permanent root group if it does not exist yet."""
        if ROOT_GROUP_ID not in self._groups:
            self._groups[ROOT_GROUP_ID] = {"name": "/", "parent_id": ""}
            self._memberships[ROOT_GROUP_ID] = set()

    # ─── ID generation ────────────────────────────────────────────────────────

    def _generate_id(self) -> str:
        gid = f"bxpg{self._id_counter}"
        self._id_counter += 1
        return gid

    # ─── Group CRUD ───────────────────────────────────────────────────────────

    def add_group(self, name: str, parent_id: str = "") -> str:
        """Create a new group and return its immutable ID.

        If *parent_id* is empty the group is created directly under the
        permanent root group.
        """
        if not parent_id:
            parent_id = ROOT_GROUP_ID
        if parent_id not in self._groups:
            raise ValueError(f"Parent group '{parent_id}' does not exist")
        gid = self._generate_id()
        self._groups[gid] = {"name": name, "parent_id": parent_id}
        self._memberships[gid] = set()
        return gid

    def remove_group(self, group_id: str) -> None:
        """Remove a group; its direct children are promoted to its parent."""
        if group_id == ROOT_GROUP_ID:
            raise ValueError("Cannot remove the root group")
        if group_id not in self._groups:
            raise KeyError(f"Group '{group_id}' does not exist")
        parent_id = self._groups[group_id]["parent_id"]
        for info in self._groups.values():
            if info["parent_id"] == group_id:
                info["parent_id"] = parent_id
        del self._groups[group_id]
        del self._memberships[group_id]

    def rename_group(self, group_id: str, new_name: str) -> None:
        """Rename a group."""
        if group_id not in self._groups:
            raise KeyError(f"Group '{group_id}' does not exist")
        self._groups[group_id]["name"] = new_name

    # ─── Membership ───────────────────────────────────────────────────────────

    def assign(self, group_ids: list, param_ids: list) -> None:
        """Add every param in *param_ids* to every group in *group_ids*."""
        for gid in group_ids:
            if gid in self._memberships:
                self._memberships[gid].update(param_ids)

    def deassign(self, group_ids: list, param_ids: list) -> None:
        """Remove every param in *param_ids* from every group in *group_ids*."""
        for gid in group_ids:
            if gid in self._memberships:
                self._memberships[gid].difference_update(param_ids)

    def remove_param_from_all_groups(self, param_id: str) -> None:
        """Remove *param_id* from every group (call when a parameter is deleted)."""
        for members in self._memberships.values():
            members.discard(param_id)

    def get_param_groups(self, param_id: str) -> list:
        """Return the list of group IDs that contain *param_id*."""
        return [
            gid for gid, members in self._memberships.items() if param_id in members
        ]

    def get_group_members(self, group_id: str) -> set:
        """Return the set of param IDs belonging to *group_id*."""
        return set(self._memberships.get(group_id, set()))

    def get_group_name(self, group_id: str) -> "str | None":
        """Return the display name of *group_id*, or ``None`` if not found."""
        info = self._groups.get(group_id)
        return info["name"] if info else None

    # ─── Tree structure ───────────────────────────────────────────────────────

    def list_groups(self) -> list:
        """Return all groups in DFS pre-order with tree metadata.

        Each entry is a dict::

            {
                "id":           str,
                "name":         str,
                "parent_id":    str,   # "" for root groups
                "tree_depth":   int,   # 0 for root
                "has_children": bool,
            }
        """
        children: dict = {gid: [] for gid in self._groups}
        roots: list = []
        for gid, info in self._groups.items():
            pid = info["parent_id"]
            if pid and pid in children:
                children[pid].append(gid)
            else:
                roots.append(gid)

        result: list = []

        def _dfs(gid: str, depth: int) -> None:
            kids = children[gid]
            result.append(
                {
                    "id": gid,
                    "name": self._groups[gid]["name"],
                    "parent_id": self._groups[gid]["parent_id"],
                    "tree_depth": depth,
                    "has_children": bool(kids),
                }
            )
            for kid in kids:
                _dfs(kid, depth + 1)

        for root in roots:
            _dfs(root, 0)

        return result

    # ─── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id_counter": self._id_counter,
            "groups": [
                {"id": gid, "name": info["name"], "parent_id": info["parent_id"]}
                for gid, info in self._groups.items()
                if gid != ROOT_GROUP_ID  # root is always recreated; never persisted
            ],
            "memberships": {
                gid: sorted(members)
                for gid, members in self._memberships.items()
                if gid != ROOT_GROUP_ID
            },
        }

    def load_dict(self, data: dict) -> None:
        self._id_counter = data.get("id_counter", 0)
        self._groups = {}
        self._memberships = {}
        self._ensure_root()  # always recreate root first
        memberships = data.get("memberships", {})
        for g in data.get("groups", []):
            gid = g["id"]
            if gid == ROOT_GROUP_ID:
                continue  # skip if somehow present in old data
            # Migrate legacy data where parent_id was "" (open root) → ROOT_GROUP_ID
            parent_id = g.get("parent_id", "") or ROOT_GROUP_ID
            self._groups[gid] = {"name": g["name"], "parent_id": parent_id}
            self._memberships[gid] = set(memberships.get(gid, []))

    def clear(self) -> None:
        self._id_counter = 0
        self._groups = {}
        self._memberships = {}
        self._ensure_root()
