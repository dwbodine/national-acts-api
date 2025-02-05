"""
Admin service module
"""

from common.db import db_query_all, db_insert, db_update
from common.models.admin import SiteSetting, SiteSettingType
from common.utility import move_temp_file_to_public_folder


class AdminService:
    """
    Service to handle miscellaneous site admin functions
    """

    def get_site_settings(self):
        """
        Fetch all site settings from database
        """
        settings: list[SiteSetting] = []
        sql = "SELECT * FROM Settings ORDER BY Name ASC"
        rows = db_query_all(sql)
        for row in rows:
            setting = SiteSetting()
            setting.setting_id = int(row["ID"])
            setting.name = str(row["Name"])
            setting.display_name = str(row["DisplayName"])
            setting.type = str(row["Type"])
            setting.value = str(row["Value"])
            setting.file_path = str(row["FilePath"])
            setting.dirty = False
            settings.append(setting)

        return settings

    def update_setting(self, setting: SiteSetting):
        """
        Add or update site setting to database
        """
        if setting is None:
            return False

        success: bool = True
        data = {
            "name": setting.name,
            "displayName": setting.display_name,
            "type": setting.type,
            "value": setting.value,
        }
        if setting.setting_id is None or setting.setting_id <= 0:
            sql = """INSERT INTO Settings (Name, DisplayName, Type, Value)
                     VALUES(%(name)s, %(displayName)s, %(type)s, %(value)s)"""
            setting_id = db_insert(sql, data)
            success = setting_id > 0
        else:
            sql = """UPDATE Settings
                        SET Name=%(name)s, 
                        DisplayName=%(displayName)s,
                        Type=%(type)s, 
                        Value=%(value)s, 
                        LastUpdated=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE ID=%(setting_id)s"""
            data["setting_id"] = setting.setting_id
            success = db_update(sql, data)

        # move temp image to final place
        if setting.type == SiteSettingType.IMAGE:
            move_temp_file_to_public_folder(setting.value, setting.file_path)

        return success
