"""
Unit tests for common.role_service helpers.
"""

from common import role_service
from common.models.user import Permission, Role


def create_permission(permission_id, permission_name):
    """
    Create a Permission instance for tests.
    """
    return Permission(permission_id, permission_name)


def create_role(role_id=0, role_name="Manager", permissions=None):
    """
    Create a Role instance for tests.
    """
    role = Role()
    role.role_id = role_id
    role.role_name = role_name
    role.permissions = permissions or []
    return role


def test_get_all_permissions_maps_permission_rows(monkeypatch):
    """
    Test that get_all_permissions maps database rows into Permission objects.
    """
    monkeypatch.setattr(
        role_service,
        "db_query_all",
        lambda sql: [
            {"PermissionId": 2, "PermissionName": "Edit"},
            {"PermissionId": 3, "PermissionName": "Delete"},
        ],
    )

    permissions = role_service.RoleService().get_all_permissions()

    assert [permission.permission_id for permission in permissions] == [2, 3]
    assert [permission.permission_name for permission in permissions] == [
        "Edit",
        "Delete",
    ]


def test_get_all_roles_maps_roles_and_loads_permissions(monkeypatch):
    """
    Test that get_all_roles maps roles and loads permissions for each role.
    """
    monkeypatch.setattr(
        role_service,
        "db_query_all",
        lambda sql: [
            {"RoleId": 2, "RoleName": "Manager"},
            {"RoleId": 3, "RoleName": "Viewer"},
        ],
    )
    monkeypatch.setattr(
        role_service.RoleService,
        "get_permissions_for_role",
        lambda self, role_id: [
            create_permission(role_id * 10, f"Permission {role_id}")
        ],
    )

    roles = role_service.RoleService().get_all_roles()

    assert [role.role_id for role in roles] == [2, 3]
    assert roles[0].permissions[0].permission_id == 20
    assert roles[1].permissions[0].permission_name == "Permission 3"


def test_get_role_by_id_returns_role_with_permissions(monkeypatch):
    """
    Test that get_role_by_id returns a mapped role and its permissions.
    """
    monkeypatch.setattr(
        role_service,
        "db_query_one",
        lambda sql, data: {"RoleId": 4, "RoleName": "Reporter"},
    )
    monkeypatch.setattr(
        role_service.RoleService,
        "get_permissions_for_role",
        lambda self, role_id: [create_permission(1, "Read")],
    )

    role = role_service.RoleService().get_role_by_id(4)

    assert role is not None
    assert role.role_id == 4
    assert role.role_name == "Reporter"
    assert role.permissions[0].permission_name == "Read"


def test_get_role_by_id_returns_none_when_row_is_missing(monkeypatch):
    """
    Test that get_role_by_id returns None when the requested role is not found.
    """
    monkeypatch.setattr(role_service, "db_query_one", lambda sql, data: None)

    role = role_service.RoleService().get_role_by_id(4)

    assert role is None


def test_update_role_updates_existing_role_and_assigns_permissions(monkeypatch):
    """
    Test that update_role updates an existing role and reassigns permissions.
    """
    update_calls = []
    assign_calls = []
    role_to_update = create_role(
        role_id=5,
        role_name="Updated Manager",
        permissions=[create_permission(2, "Edit")],
    )
    monkeypatch.setattr(
        role_service.RoleService,
        "get_role_by_id",
        lambda self, role_id: create_role(role_id=5, role_name="Manager"),
    )
    monkeypatch.setattr(
        role_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        role_service.RoleService,
        "assign_permissions_to_role_id",
        lambda self, role_id, permissions: assign_calls.append((role_id, permissions))
        or True,
    )

    success = role_service.RoleService().update_role(role_to_update)

    assert success is True
    assert update_calls[0][1] == {"roleName": "Updated Manager", "roleId": 5}
    assert assign_calls == [(5, role_to_update.permissions)]


def test_update_role_inserts_new_role_and_assigns_permissions(monkeypatch):
    """
    Test that update_role inserts new roles and assigns permissions when the insert succeeds.
    """
    insert_calls = []
    assign_calls = []
    role_to_update = create_role(
        role_id=0,
        role_name="New Role",
        permissions=[create_permission(3, "Delete")],
    )
    monkeypatch.setattr(
        role_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 6,
    )
    monkeypatch.setattr(
        role_service.RoleService,
        "assign_permissions_to_role_id",
        lambda self, role_id, permissions: assign_calls.append((role_id, permissions))
        or True,
    )

    success = role_service.RoleService().update_role(role_to_update)

    assert success is True
    assert insert_calls[0][1] == {"roleName": "New Role"}
    assert assign_calls == [(6, role_to_update.permissions)]


def test_update_role_returns_false_when_existing_role_update_fails(monkeypatch):
    """
    Test that update_role returns False when updating an existing role row fails.
    """
    assign_calls = []
    role_to_update = create_role(
        role_id=5,
        role_name="Updated Manager",
        permissions=[create_permission(2, "Edit")],
    )
    monkeypatch.setattr(
        role_service.RoleService,
        "get_role_by_id",
        lambda self, role_id: create_role(role_id=5, role_name="Manager"),
    )
    monkeypatch.setattr(role_service, "db_update", lambda sql, data: False)
    monkeypatch.setattr(
        role_service.RoleService,
        "assign_permissions_to_role_id",
        lambda self, role_id, permissions: assign_calls.append((role_id, permissions))
        or True,
    )

    success = role_service.RoleService().update_role(role_to_update)

    assert success is False
    assert not assign_calls


def test_update_role_returns_true_when_inserted_role_id_is_one(monkeypatch):
    """
    Test that update_role returns True without assigning permissions when the inserted role id is one.
    """
    assign_calls = []
    role_to_update = create_role(
        role_id=0,
        role_name="New Role",
        permissions=[create_permission(3, "Delete")],
    )
    monkeypatch.setattr(role_service, "db_insert", lambda sql, data: 1)
    monkeypatch.setattr(
        role_service.RoleService,
        "assign_permissions_to_role_id",
        lambda self, role_id, permissions: assign_calls.append((role_id, permissions))
        or True,
    )

    success = role_service.RoleService().update_role(role_to_update)

    assert success is True
    assert not assign_calls


def test_update_role_returns_false_when_role_is_none():
    """
    Test that update_role returns False when no role object is provided.
    """
    assert role_service.RoleService().update_role(None) is False


def test_delete_roles_deletes_permissions_then_roles(monkeypatch):
    """
    Test that delete_roles removes role permissions before deleting roles.
    """
    delete_calls = []
    monkeypatch.setattr(
        role_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    success = role_service.RoleService().delete_roles([2, 3])

    assert success is True
    assert "DELETE FROM RolePermissions" in delete_calls[0][0]
    assert "DELETE FROM Roles" in delete_calls[1][0]
    assert delete_calls[0][1] == {"roleList": "2,3"}


def test_delete_roles_returns_true_for_empty_role_lists():
    """
    Test that delete_roles returns True when there are no roles to delete.
    """
    success = role_service.RoleService().delete_roles([])

    assert success is True


def test_delete_roles_returns_false_when_permission_delete_fails(monkeypatch):
    """
    Test that delete_roles stops when deleting role permissions fails.
    """
    delete_calls = []
    monkeypatch.setattr(
        role_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or False,
    )

    success = role_service.RoleService().delete_roles([2, 3])

    assert success is False
    assert len(delete_calls) == 1
    assert "DELETE FROM RolePermissions" in delete_calls[0][0]


def test_get_permissions_for_role_returns_all_permissions_for_admin_role(
    monkeypatch,
):
    """
    Test that get_permissions_for_role returns
    all permissions for role ids less than or equal to one.
    """
    calls = []
    monkeypatch.setattr(
        role_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [{"PermissionId": 1, "PermissionName": "Read"}],
    )

    permissions = role_service.RoleService().get_permissions_for_role(1)

    assert len(permissions) == 1
    assert "JOIN RolePermissions" not in calls[0][0]


def test_get_permissions_for_role_returns_empty_for_none_role_id():
    """
    Test that get_permissions_for_role returns an empty list when the role id is None.
    """
    permissions = role_service.RoleService().get_permissions_for_role(None)

    assert not permissions


def test_get_permissions_for_role_uses_role_permission_join_for_non_admin_roles(
    monkeypatch,
):
    """
    Test that get_permissions_for_role queries role-specific permissions for non-admin roles.
    """
    calls = []
    monkeypatch.setattr(
        role_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [{"PermissionId": 2, "PermissionName": "Edit"}],
    )

    permissions = role_service.RoleService().get_permissions_for_role(5)

    assert len(permissions) == 1
    assert "JOIN RolePermissions" in calls[0][0]
    assert calls[0][1] == {"roleId": 5}


def test_assign_permissions_to_role_id_deletes_removed_and_inserts_new_permissions(
    monkeypatch,
):
    """
    Test that assign_permissions_to_role_id removes old permissions and inserts new ones.
    """
    delete_calls = []
    insert_calls = []
    existing_role = create_role(
        role_id=5,
        permissions=[create_permission(1, "Read"), create_permission(2, "Edit")],
    )
    new_permissions = [create_permission(2, "Edit"), create_permission(3, "Delete")]
    monkeypatch.setattr(
        role_service.RoleService,
        "get_role_by_id",
        lambda self, role_id: existing_role,
    )
    monkeypatch.setattr(
        role_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        role_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 44,
    )

    success = role_service.RoleService().assign_permissions_to_role_id(
        5, new_permissions
    )

    assert success is True
    assert delete_calls[0][1] == {"permissionId": 1, "roleId": 5}
    assert insert_calls[0][1] == {"roleId": 5, "permissionId": 3}


def test_assign_permissions_to_role_id_returns_true_when_role_lookup_is_missing(
    monkeypatch,
):
    """
    Test that assign_permissions_to_role_id returns True when the role lookup returns nothing.
    """
    monkeypatch.setattr(
        role_service.RoleService,
        "get_role_by_id",
        lambda self, role_id: None,
    )

    success = role_service.RoleService().assign_permissions_to_role_id(
        5,
        [create_permission(1, "Read")],
    )

    assert success is True


def test_assign_permissions_to_role_id_keeps_matching_permissions_without_writes(
    monkeypatch,
):
    """
    Test that assign_permissions_to_role_id performs no writes when permissions already match.
    """
    delete_calls = []
    insert_calls = []
    existing_role = create_role(
        role_id=5,
        permissions=[create_permission(2, "Edit")],
    )
    monkeypatch.setattr(
        role_service.RoleService,
        "get_role_by_id",
        lambda self, role_id: existing_role,
    )
    monkeypatch.setattr(
        role_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        role_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 44,
    )

    success = role_service.RoleService().assign_permissions_to_role_id(
        5,
        [create_permission(2, "Edit")],
    )

    assert success is True
    assert not delete_calls
    assert not insert_calls


def test_assign_permissions_to_role_id_skips_non_positive_permission_ids(monkeypatch):
    """
    Test that assign_permissions_to_role_id skips inserts for non-positive permission ids.
    """
    existing_role = create_role(role_id=5, permissions=[])
    insert_calls = []
    monkeypatch.setattr(
        role_service.RoleService,
        "get_role_by_id",
        lambda self, role_id: existing_role,
    )
    monkeypatch.setattr(
        role_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 44,
    )

    success = role_service.RoleService().assign_permissions_to_role_id(
        5,
        [create_permission(0, "Ignore")],
    )

    assert success is True
    assert not insert_calls


def test_assign_permissions_to_role_id_skips_missing_permission_matches(monkeypatch):
    """
    Test that assign_permissions_to_role_id skips inserts when a positive permission id no longer matches a permission object.
    """

    class ChangingPermission:
        """
        Permission-like object that changes ids between reads.
        """

        def __init__(self):
            self.read_count = 0

        @property
        def permission_id(self):
            """
            Return different ids across reads to simulate a missing permission match.
            """
            self.read_count += 1
            return 3 if self.read_count == 1 else 4

    existing_role = create_role(role_id=5, permissions=[])
    insert_calls = []
    monkeypatch.setattr(
        role_service.RoleService,
        "get_role_by_id",
        lambda self, role_id: existing_role,
    )
    monkeypatch.setattr(
        role_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 44,
    )

    success = role_service.RoleService().assign_permissions_to_role_id(
        5,
        [ChangingPermission()],
    )

    assert success is True
    assert not insert_calls


def test_assign_permissions_to_role_id_rejects_invalid_role_ids():
    """
    Test that assign_permissions_to_role_id returns False for invalid role ids.
    """
    success = role_service.RoleService().assign_permissions_to_role_id(
        0,
        [create_permission(1, "Read")],
    )

    assert success is False


def test_get_user_seller_permissions_returns_permission_ids(monkeypatch):
    """
    Test that get_user_seller_permissions returns ordered permission ids for a user-seller row.
    """
    monkeypatch.setattr(
        role_service,
        "db_query_all",
        lambda sql, data: [{"PermissionId": 2}, {"PermissionId": 5}],
    )

    permissions = role_service.RoleService().get_user_seller_permissions(10)

    assert permissions == [2, 5]


def test_get_user_seller_permissions_rejects_invalid_ids():
    """
    Test that get_user_seller_permissions returns an empty list for invalid user-seller ids.
    """
    permissions = role_service.RoleService().get_user_seller_permissions(1)

    assert not permissions
