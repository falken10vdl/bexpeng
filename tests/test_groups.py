# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Tests for GroupManager."""

import pytest

from bexpeng.groups import GroupManager, ROOT_GROUP_ID


def _ug(gm):
    """Return only user-created groups (exclude the permanent root)."""
    return [g for g in gm.list_groups() if g["id"] != ROOT_GROUP_ID]


@pytest.fixture(autouse=True)
def fresh():
    GroupManager.reset_instance()
    yield
    GroupManager.reset_instance()


class TestGroupCRUD:
    def test_add_root_group(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Geometry")
        assert gid == "bxpg0"
        assert gm.get_group_name(gid) == "Geometry"

    def test_add_child_group(self):
        gm = GroupManager.get_instance()
        parent = gm.add_group("Geometry")
        child = gm.add_group("Walls", parent_id=parent)
        ug = _ug(gm)
        assert len(ug) == 2
        assert ug[1]["tree_depth"] == 2
        assert ug[1]["parent_id"] == parent

    def test_add_invalid_parent_raises(self):
        gm = GroupManager.get_instance()
        with pytest.raises(ValueError):
            gm.add_group("Child", parent_id="nonexistent")

    def test_id_increments(self):
        gm = GroupManager.get_instance()
        g1 = gm.add_group("A")
        g2 = gm.add_group("B")
        assert g1 == "bxpg0"
        assert g2 == "bxpg1"

    def test_remove_group(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Geometry")
        gm.remove_group(gid)
        assert _ug(gm) == []

    def test_remove_nonexistent_raises(self):
        gm = GroupManager.get_instance()
        with pytest.raises(KeyError):
            gm.remove_group("bxpg99")

    def test_remove_promotes_children_to_removed_groups_parent(self):
        gm = GroupManager.get_instance()
        parent = gm.add_group("Geometry")
        child = gm.add_group("Walls", parent_id=parent)
        gm.remove_group(parent)
        ug = _ug(gm)
        assert len(ug) == 1
        assert ug[0]["id"] == child
        assert ug[0]["parent_id"] == ROOT_GROUP_ID
        assert ug[0]["tree_depth"] == 1

    def test_remove_promotes_to_intermediate_parent(self):
        gm = GroupManager.get_instance()
        root = gm.add_group("Root")
        mid = gm.add_group("Mid", parent_id=root)
        leaf = gm.add_group("Leaf", parent_id=mid)
        gm.remove_group(mid)
        groups = {g["id"]: g for g in gm.list_groups()}
        assert groups[leaf]["parent_id"] == root
        assert groups[leaf]["tree_depth"] == 2

    def test_rename_group(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("OldName")
        gm.rename_group(gid, "NewName")
        assert gm.get_group_name(gid) == "NewName"

    def test_rename_nonexistent_raises(self):
        gm = GroupManager.get_instance()
        with pytest.raises(KeyError):
            gm.rename_group("bxpg99", "Name")

    def test_get_group_name_unknown_returns_none(self):
        gm = GroupManager.get_instance()
        assert gm.get_group_name("bxpg99") is None

    def test_remove_root_raises(self):
        gm = GroupManager.get_instance()
        with pytest.raises(ValueError):
            gm.remove_group(ROOT_GROUP_ID)


class TestMembership:
    def test_assign_and_get_members(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Geometry")
        gm.assign([gid], ["bxp0", "bxp1"])
        assert gm.get_group_members(gid) == {"bxp0", "bxp1"}

    def test_assign_does_not_duplicate(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Geometry")
        gm.assign([gid], ["bxp0"])
        gm.assign([gid], ["bxp0"])
        assert len(gm.get_group_members(gid)) == 1

    def test_assign_multiple_groups(self):
        gm = GroupManager.get_instance()
        g1 = gm.add_group("A")
        g2 = gm.add_group("B")
        gm.assign([g1, g2], ["bxp0"])
        assert "bxp0" in gm.get_group_members(g1)
        assert "bxp0" in gm.get_group_members(g2)

    def test_deassign(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Geometry")
        gm.assign([gid], ["bxp0", "bxp1"])
        gm.deassign([gid], ["bxp0"])
        assert gm.get_group_members(gid) == {"bxp1"}

    def test_deassign_nonmember_is_noop(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Geometry")
        gm.deassign([gid], ["bxp_not_a_member"])  # must not raise

    def test_get_param_groups(self):
        gm = GroupManager.get_instance()
        g1 = gm.add_group("A")
        g2 = gm.add_group("B")
        gm.assign([g1, g2], ["bxp0"])
        result = gm.get_param_groups("bxp0")
        assert set(result) == {g1, g2}

    def test_get_param_groups_empty(self):
        gm = GroupManager.get_instance()
        gm.add_group("A")
        assert gm.get_param_groups("bxp_orphan") == []

    def test_remove_param_from_all_groups(self):
        gm = GroupManager.get_instance()
        g1 = gm.add_group("A")
        g2 = gm.add_group("B")
        gm.assign([g1, g2], ["bxp0", "bxp1"])
        gm.remove_param_from_all_groups("bxp0")
        assert "bxp0" not in gm.get_group_members(g1)
        assert "bxp0" not in gm.get_group_members(g2)
        assert "bxp1" in gm.get_group_members(g1)

    def test_get_members_of_nonexistent_group(self):
        gm = GroupManager.get_instance()
        assert gm.get_group_members("bxpg99") == set()

    def test_assign_ignores_unknown_group(self):
        gm = GroupManager.get_instance()
        # Should not raise even though "bxpg99" is unknown
        gm.assign(["bxpg99"], ["bxp0"])

    def test_removed_group_not_in_param_groups(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Geometry")
        gm.assign([gid], ["bxp0"])
        gm.remove_group(gid)
        assert gid not in gm.get_param_groups("bxp0")


class TestTreeOrder:
    def test_single_root(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("Root")
        ug = _ug(gm)
        assert len(ug) == 1
        assert ug[0]["id"] == gid
        assert ug[0]["tree_depth"] == 1
        assert ug[0]["has_children"] is False

    def test_dfs_order(self):
        gm = GroupManager.get_instance()
        root = gm.add_group("Root")
        child1 = gm.add_group("Child1", parent_id=root)
        grandchild = gm.add_group("Grandchild", parent_id=child1)
        child2 = gm.add_group("Child2", parent_id=root)
        ids = [g["id"] for g in _ug(gm)]
        assert ids == [root, child1, grandchild, child2]

    def test_tree_depth(self):
        gm = GroupManager.get_instance()
        root = gm.add_group("Root")
        child = gm.add_group("Child", parent_id=root)
        grand = gm.add_group("Grandchild", parent_id=child)
        depths = {g["id"]: g["tree_depth"] for g in gm.list_groups()}
        assert depths[root] == 1
        assert depths[child] == 2
        assert depths[grand] == 3

    def test_has_children_flag(self):
        gm = GroupManager.get_instance()
        parent = gm.add_group("Parent")
        child = gm.add_group("Child", parent_id=parent)
        info = {g["id"]: g for g in gm.list_groups()}
        assert info[parent]["has_children"] is True
        assert info[child]["has_children"] is False

    def test_multiple_roots(self):
        gm = GroupManager.get_instance()
        r1 = gm.add_group("R1")
        r2 = gm.add_group("R2")
        c1 = gm.add_group("C1", parent_id=r1)
        ids = [g["id"] for g in _ug(gm)]
        assert ids == [r1, c1, r2]

    def test_empty_list(self):
        gm = GroupManager.get_instance()
        assert _ug(gm) == []
        # root group is always present
        assert len(gm.list_groups()) == 1
        assert gm.list_groups()[0]["id"] == ROOT_GROUP_ID

    def test_remove_then_list(self):
        gm = GroupManager.get_instance()
        r1 = gm.add_group("R1")
        c1 = gm.add_group("C1", parent_id=r1)
        gm.remove_group(r1)
        ug = _ug(gm)
        assert len(ug) == 1
        assert ug[0]["id"] == c1
        assert ug[0]["tree_depth"] == 1


class TestSerialization:
    def test_round_trip(self):
        gm = GroupManager.get_instance()
        root = gm.add_group("Geometry")
        child = gm.add_group("Walls", parent_id=root)
        gm.assign([root], ["bxp0", "bxp1"])
        gm.assign([child], ["bxp0"])

        data = gm.to_dict()

        GroupManager.reset_instance()
        gm2 = GroupManager.get_instance()
        gm2.load_dict(data)

        assert gm2.get_group_name(root) == "Geometry"
        assert gm2.get_group_name(child) == "Walls"
        assert gm2.get_group_members(root) == {"bxp0", "bxp1"}
        assert gm2.get_group_members(child) == {"bxp0"}
        groups = gm2.list_groups()
        assert groups[1]["id"] == root
        assert groups[2]["id"] == child
        assert groups[2]["parent_id"] == root
        assert groups[2]["tree_depth"] == 2

    def test_id_counter_preserved(self):
        gm = GroupManager.get_instance()
        gm.add_group("A")
        gm.add_group("B")
        data = gm.to_dict()

        GroupManager.reset_instance()
        gm2 = GroupManager.get_instance()
        gm2.load_dict(data)

        new_id = gm2.add_group("C")
        assert new_id == "bxpg2"

    def test_empty_round_trip(self):
        gm = GroupManager.get_instance()
        data = gm.to_dict()

        GroupManager.reset_instance()
        gm2 = GroupManager.get_instance()
        gm2.load_dict(data)

        assert _ug(gm2) == []

    def test_clear(self):
        gm = GroupManager.get_instance()
        gm.add_group("A")
        gm.add_group("B")
        gm.clear()
        assert _ug(gm) == []
        assert gm._id_counter == 0
        # root is recreated
        assert gm.list_groups()[0]["id"] == ROOT_GROUP_ID

    def test_to_dict_memberships_are_sorted(self):
        gm = GroupManager.get_instance()
        gid = gm.add_group("G")
        gm.assign([gid], ["bxp2", "bxp0", "bxp1"])
        data = gm.to_dict()
        assert data["memberships"][gid] == sorted(["bxp2", "bxp0", "bxp1"])
