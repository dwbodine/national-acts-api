"""
Role/permissions service module
"""

from common.models.user import (
    Role,
    Permission,
)
from common.db import db_query_all, db_query_one, db_update, db_insert, db_delete
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class RoleService:
    """
    Service to deal with user operations
    """

    # PUBLIC METHODS
    def get_all_permissions(self):
        """
        Get all permissions in the system
        """
        permissions: list[Permission] = []
        sql = """SELECT * FROM Permissions ORDER BY PermissionName"""
        rows = db_query_all(sql)
        for row in rows:
            permission_id = get_override_int_value_or_default(row["PermissionId"])
            name = get_override_string_value_or_default(row["PermissionName"])
            permission = Permission(permission_id, name)
            permissions.append(permission)
        return permissions

    def get_all_roles(self):
        """
        Get all roles in the system
        """
        roles: list[Role] = []
        sql = """SELECT * FROM Roles ORDER BY RoleId"""
        rows = db_query_all(sql)
        for row in rows:
            role_id = get_override_int_value_or_default(row["RoleId"])
            role_name = get_override_string_value_or_default(row["RoleName"])
            role = Role()
            role.role_id = role_id
            role.role_name = role_name
            permissions = self.get_permissions_for_role(role_id)
            role.permissions = permissions
            roles.append(role)
        return roles

    def get_role_by_id(self, role_id: int):
        """
        Get role by role_id
        """
        role: Role = None
        sql = """SELECT * FROM Roles WHERE RoleId=%(roleId)s"""
        data = {"roleId": role_id}
        row = db_query_one(sql, data)
        if row:
            role_id = get_override_int_value_or_default(row["RoleId"])
            role_name = get_override_string_value_or_default(row["RoleName"])
            role = Role()
            role.role_id = role_id
            role.role_name = role_name
            permissions = self.get_permissions_for_role(role_id)
            role.permissions = permissions
        return role

    def update_role(self, role_to_update: Role):
        """
        Update or Create role
        """
        success: bool = True
        if role_to_update is None:
            return False
        existing_role: Role = None
        new_role_id: int = get_override_int_value_or_default(role_to_update.role_id)
        if new_role_id > 0:
            existing_role = self.get_role_by_id(new_role_id)
        if existing_role is not None:
            existing_role_id = get_override_int_value_or_default(existing_role.role_id)
            update_sql = """UPDATE Roles SET RoleName=%(roleName)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE RoleId=%(roleId)s"""
            update_data = {
                "roleName": get_override_string_value_or_default(
                    role_to_update.role_name
                ),
                "roleId": existing_role_id,
            }
            success = db_update(update_sql, update_data)
            if success is True:
                success = self.assign_permissions_to_role_id(
                    existing_role_id, role_to_update.permissions
                )
        else:
            insert_sql = """INSERT INTO Roles (RoleName, LastUpdate)
                        VALUES (%(roleName)s, CURRENT_TIMESTAMP)"""
            insert_data = {
                "roleName": get_override_string_value_or_default(
                    role_to_update.role_name
                )
            }
            role_id = db_insert(insert_sql, insert_data)
            if role_id > 1:
                success = self.assign_permissions_to_role_id(
                    role_id, role_to_update.permissions
                )
        return success

    def delete_roles(self, role_ids_to_delete: list[int]):
        """
        Delete list of roles
        """
        success: bool = True
        if len(role_ids_to_delete) > 0:
            role_id_list = ",".join(str(x) for x in role_ids_to_delete)
            delete_permission_sql = (
                """DELETE FROM RolePermissions WHERE RoleId IN (%(roleList)s)"""
            )
            delete_role_data = {"roleList": role_id_list}
            success = db_delete(delete_permission_sql, delete_role_data)
            if success is True:
                delete_row_sql = """DELETE FROM Roles WHERE RoleId IN (%(roleList)s)"""
                success = db_delete(delete_row_sql, delete_role_data)
        return success

    def get_permissions_for_role(self, role_id: int):
        """
        Get Permissions associated with a role id
        """
        permissions: list[Permission] = []
        if role_id is None:
            return permissions

        sql = ""
        if role_id > 1:
            sql = """SELECT Permissions.PermissionId, Permissions.PermissionName
                     FROM Permissions 
                    JOIN RolePermissions
                        ON RolePermissions.PermissionId = Permissions.PermissionId 
                    WHERE RolePermissions.RoleId=%(roleId)s"""
        else:
            sql = """SELECT Permissions.PermissionId, Permissions.PermissionName
                     FROM Permissions"""

        data = {"roleId": role_id}
        rows = db_query_all(sql, data)
        for row in rows:
            permission_id = get_override_int_value_or_default(row["PermissionId"])
            permission_name = get_override_string_value_or_default(
                row["PermissionName"]
            )
            permission = Permission(permission_id, permission_name)
            permissions.append(permission)
        return permissions

    def assign_permissions_to_role_id(
        self, role_id: int, new_permissions: list[Permission]
    ):
        """
        Update permissions for selected role
        """
        if role_id is None or role_id <= 0:
            return False
        existing_role = self.get_role_by_id(role_id)
        success: bool = True
        if existing_role is not None:
            new_permission_ids = [
                permission.permission_id for permission in new_permissions
            ]
            for existing_permission in existing_role.permissions:
                existing_permission_id = existing_permission.permission_id
                if existing_permission_id in new_permission_ids:
                    new_permission_ids.remove(existing_permission_id)
                else:
                    delete_row_sql = """DELETE FROM RolePermissions
                                    WHERE RoleId=%(roleId)s
                                    AND PermissionId=%(permissionId)s"""
                    delete_role_data = {
                        "permissionId": existing_permission_id,
                        "roleId": role_id,
                    }
                    success = db_delete(delete_row_sql, delete_role_data)
            if len(new_permission_ids) > 0:
                for new_permission_id in new_permission_ids:
                    if new_permission_id > 0:
                        new_permission: Permission = (
                            self.__get_permission_from_list_by_id(
                                new_permissions, new_permission_id
                            )
                        )
                        if new_permission is not None:
                            insert_permission_sql = """INSERT INTO RolePermissions
                                            (RoleId, PermissionId, LastUpdate)
                                            VALUES (%(roleId)s, %(permissionId)s,
                                            CURRENT_TIMESTAMP)"""
                            insert_permission_data = {
                                "roleId": get_override_int_value_or_default(role_id),
                                "permissionId": get_override_int_value_or_default(
                                    new_permission_id
                                ),
                            }
                            role_permission_id = db_insert(
                                insert_permission_sql, insert_permission_data
                            )
                            success = role_permission_id > 0
        return success

    def __get_permission_from_list_by_id(
        self, permissions: list[Permission], permission_id: int
    ):
        """
        Filter one permission from list by id
        """
        permission: Permission = None
        for p in permissions:
            if p.permission_id == permission_id:
                permission = p
                break
        return permission

    def get_user_seller_permissions(self, user_seller_id: int):
        """
        Get permissions for user by seller
        """
        permissions: list[int] = []
        if user_seller_id is None or user_seller_id <= 1:
            return permissions

        sql = """SELECT Permissions.PermissionId FROM Permissions
                    JOIN RolePermissions ON RolePermissions.PermissionId = Permissions.PermissionId 
                    JOIN UserSeller ON UserSeller.RoleId = RolePermissions.RoleId 
                    WHERE UserSeller.UserSellerId=%(userSellerId)s 
                    ORDER BY Permissions.PermissionId"""
        data = {"userSellerId": user_seller_id}

        rows = db_query_all(sql, data)

        for row in rows:
            permission_id = get_override_int_value_or_default(row["PermissionId"])
            permissions.append(permission_id)

        return permissions
