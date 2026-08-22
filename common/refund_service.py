"""
Service to pull refund policies from database
"""

from common.db import db_query_all, db_update
from common.models.admin import RefundCategory, RefundPolicy
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class RefundService:
    """
    Pulls refund policy data from database
    """

    def get_refund_policy_by_category_id(self, category_id: int):
        """
        Get refund policy by category
        """

        refund_policies: list[RefundPolicy] = []
        sql: str = """SELECT RefundPolicy.*, RefundCategory.CategoryName
                        FROM RefundPolicy
                        JOIN RefundCategory 
                            ON RefundCategory.RefundCategoryId = RefundPolicy.RefundCategoryId"""

        data = {}
        if category_id > 0:
            sql += """ WHERE RefundPolicy.RefundCategoryId=%(category_id)s
                        ORDER BY RefundPolicy.RefundPolicyId ASC"""
            data["category_id"] = category_id
        else:
            sql += """ ORDER BY RefundPolicy.RefundCategoryId ASC"""

        rows = db_query_all(sql, data)
        for row in rows:
            refund_policy = self.__parse_refund_policy_from_row_dict(row)
            refund_policies.append(refund_policy)
        return refund_policies

    def update_refund_policy(self, refund_policy_to_update: RefundPolicy):
        """
        Add or update Refund Policy
        """
        data = {
            "category_id": refund_policy_to_update.category.refund_category_id,
            "policy_text": refund_policy_to_update.policy_text,
        }
        sql: str = None
        success: bool = False
        if refund_policy_to_update.refund_policy_id > 0:
            data["refund_policy_id"] = refund_policy_to_update.refund_policy_id
            sql = """UPDATE RefundPolicy SET
					    RefundCategoryId=%(category_id)s,                      
						RefundPolicy=%(policy_text)s,
                        LastUpdate=CURRENT_TIMESTAMP
                    where RefundPolicyId=%(refund_policy_id)s"""
            success = db_update(sql, data)

        return success

    def get_refund_categories(self):
        """
        Return all refund policy categories
        """
        categories: list[RefundCategory] = []
        sql = """SELECT * FROM RefundCategory
                    ORDER BY RefundCategoryId ASC"""
        rows = db_query_all(sql)
        for row in rows:
            category = RefundCategory()
            category.refund_category_id = get_override_int_value_or_default(
                row["RefundCategoryId"]
            )
            category.category_name = get_override_string_value_or_default(
                row["CategoryName"]
            )
            categories.append(category)
        return categories

    def __parse_refund_policy_from_row_dict(self, row: dict):
        """
        Helper method to parse faq object
        """
        refund_policy = RefundPolicy()
        refund_policy.refund_policy_id = get_override_int_value_or_default(
            row["RefundPolicyId"]
        )
        refund_policy.policy_text = get_override_string_value_or_default(
            row["RefundPolicy"]
        )
        category = RefundCategory()
        category.refund_category_id = get_override_int_value_or_default(
            row["RefundCategoryId"]
        )
        category.category_name = get_override_string_value_or_default(
            row["CategoryName"]
        )
        refund_policy.category = category
        return refund_policy
