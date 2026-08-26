"""
Service to pull faq from database
"""

from common.db import db_delete, db_query_all, db_query_one, db_insert, db_update
from common.models.admin import Faq, FaqCategory
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class FaqService:
    """
    Pulls exchange faq data from database
    """

    def get_faq_by_category_id(self, category_id: int):
        """
        Get FAQ by category
        """

        faqs: list[Faq] = []
        sql: str = """SELECT FAQ.*, FAQCategory.CategoryName
                        FROM FAQ
                        JOIN FAQCategory 
                            ON FAQCategory.FAQCategoryID=FAQ.FAQCategoryID"""

        data = {}
        if category_id > 0:
            sql += """ WHERE FAQ.FAQCategoryID=%(category_id)s
                        ORDER BY FAQ.QuestionOrder ASC"""
            data["category_id"] = category_id
        else:
            sql += """ ORDER BY FAQ.FAQCategoryID ASC, FAQ.QuestionOrder ASC"""

        rows = db_query_all(sql, data)
        for row in rows:
            faq = self.__parse_faq_from_row_dict(row)
            faqs.append(faq)
        return faqs

    def update_faq(self, faq_to_update: Faq):
        """
        Add or update FAQ
        """
        data = {
            "category_id": faq_to_update.category.category_id,
            "question": faq_to_update.question,
            "answer": faq_to_update.answer,
        }
        sql: str = None
        success: bool = False
        if faq_to_update.faq_id > 0:
            data["faq_id"] = faq_to_update.faq_id
            data["order"] = faq_to_update.order
            sql = """UPDATE FAQ SET
					    FAQCategoryId=%(category_id)s, 
						QuestionOrder=%(order)s, 
  					 	QuestionText=%(question)s, 
						AnswerHTML=%(answer)s
                    where FAQID=%(faq_id)s"""
            success = db_update(sql, data)
        else:
            last_number = self.get_last_question_number(
                faq_to_update.category.category_id
            )
            if last_number > 0:
                data["order"] = last_number + 1
            else:
                data["order"] = 1

            sql = """INSERT INTO FAQ (FAQCategoryId, QuestionOrder,
                        QuestionText, AnswerHTML) 
                    VALUES (%(category_id)s, %(order)s,
                        %(question)s, %(answer)s)"""
            faq_id = db_insert(sql, data)
            success = faq_id > 0
        return success

    def get_last_question_number(self, category_id: int):
        """
        Get the last queston number for a particular category
        """
        last_number: int = 0
        sql = """SELECT Max(QuestionOrder) AS LastNumber
                FROM FAQ WHERE FAQCategoryID=%(category_id)s"""
        data = {"category_id": category_id}
        row = db_query_one(sql, data)
        if row:
            last_number = get_override_int_value_or_default(row["LastNumber"])
        return last_number

    def delete_faq(self, faq_id: int):
        """
        Delete FAQ
        """
        success: bool = True
        sql = """SELECT FAQCategoryID, QuestionOrder FROM FAQ WHERE FAQID=%(faq_id)s"""
        data = {"faq_id": faq_id}
        category_id: int = 0
        row = db_query_one(sql, data)
        if row:
            category_id = get_override_int_value_or_default(row["FAQCategoryID"])
            sql = """DELETE FROM FAQ WHERE FAQID=%(faq_id)s"""
            data = {"faq_id": faq_id}
            success = db_delete(sql, data)
            if success:
                success = self.__renumber_faqs(category_id)
        return success

    def get_faq_categories(self):
        """
        Return all FAQ categories
        """
        categories: list[FaqCategory] = []
        sql = """SELECT * FROM FAQCategory
                    ORDER BY FAQCategoryID ASC"""
        rows = db_query_all(sql)
        for row in rows:
            category = FaqCategory()
            category.category_id = get_override_int_value_or_default(
                row["FAQCategoryID"]
            )
            category.category_name = get_override_string_value_or_default(
                row["CategoryName"]
            )
            categories.append(category)
        return categories

    def move_down(self, faq_id: int):
        """
        Move faq down in list
        """
        success: bool = False
        sql = """SELECT FAQCategoryID, QuestionOrder FROM FAQ WHERE FAQID=%(faq_id)s"""
        data = {"faq_id": faq_id}
        category_id: int = 0
        order: int = 0
        row = db_query_one(sql, data)
        if row:
            category_id = get_override_int_value_or_default(row["FAQCategoryID"])
            order = get_override_int_value_or_default(row["QuestionOrder"])
            if category_id > 0 and order > 0:
                last_number: int = self.get_last_question_number(category_id)
                new_number: int = order + 1
                if new_number <= last_number:
                    sql2 = """SELECT FAQID
                                FROM FAQ
                                WHERE FAQCategoryID=%(category_id)s
                                    AND QuestionOrder=%(new_number)s"""
                    data2 = {"category_id": category_id, "new_number": new_number}
                    row2 = db_query_one(sql2, data2)
                    existing_id: int = 0
                    update_sql = """UPDATE FAQ
                                        SET QuestionOrder=%(new_number)s
                                        WHERE FAQID=%(faq_id)s"""
                    update_data = {"new_number": new_number, "faq_id": faq_id}
                    success = db_update(update_sql, update_data)
                    if row2:
                        existing_id = get_override_int_value_or_default(row2["FAQID"])
                        if existing_id > 0:
                            if success:
                                update_sql2 = """UPDATE FAQ
                                                    SET QuestionOrder=%(order)s
                                                    WHERE FAQID=%(existing_id)s"""
                                update_data2 = {
                                    "order": order,
                                    "existing_id": existing_id,
                                }
                                success = db_update(update_sql2, update_data2)
                    if success:
                        success = self.__renumber_faqs(category_id)
        return success

    def move_up(self, faq_id: int):
        """
        Move faq up in list
        """
        success: bool = False
        sql = """SELECT FAQCategoryID, QuestionOrder FROM FAQ WHERE FAQID=%(faq_id)s"""
        data = {"faq_id": faq_id}
        category_id: int = 0
        order: int = 0
        row = db_query_one(sql, data)
        if row:
            category_id = get_override_int_value_or_default(row["FAQCategoryID"])
            order = get_override_int_value_or_default(row["QuestionOrder"])
            if category_id > 0 and order > 0:
                new_number: int = order - 1
                if new_number > 0:
                    sql2 = """SELECT FAQID
                                FROM FAQ
                                WHERE FAQCategoryID=%(category_id)s
                                    AND QuestionOrder=%(new_number)s"""
                    data2 = {"category_id": category_id, "new_number": new_number}
                    row2 = db_query_one(sql2, data2)
                    update_sql = """UPDATE FAQ
                                        SET QuestionOrder=%(new_number)s
                                        WHERE FAQID=%(faq_id)s"""
                    update_data = {"new_number": new_number, "faq_id": faq_id}
                    success = db_update(update_sql, update_data)
                    existing_id: int = 0
                    if row2:                        
                        existing_id = get_override_int_value_or_default(row2["FAQID"])
                        if existing_id > 0:
                            if success:
                                update_sql2 = """UPDATE FAQ
                                                    SET QuestionOrder=%(order)s
                                                    WHERE FAQID=%(existing_id)s"""
                                update_data2 = {"order": order, "existing_id": existing_id}
                                success = db_update(update_sql2, update_data2)
                    if success:
                        success = self.__renumber_faqs(category_id)
        return success

    def __parse_faq_from_row_dict(self, row: dict):
        """
        Helper method to parse faq object
        """
        faq = Faq()
        faq.faq_id = get_override_int_value_or_default(row["FAQID"])
        faq.order = get_override_int_value_or_default(row["QuestionOrder"])
        faq.question = get_override_string_value_or_default(row["QuestionText"])
        faq.answer = get_override_string_value_or_default(row["AnswerHTML"])
        category = FaqCategory()
        category.category_id = get_override_int_value_or_default(row["FAQCategoryID"])
        category.category_name = get_override_string_value_or_default(
            row["CategoryName"]
        )
        faq.category = category
        return faq

    def __renumber_faqs(self, category_id: int):
        """
        Renumber FAQs in a category sequentially, starting at one.
        """
        sql = """UPDATE FAQ AS faq
                        JOIN (
                            SELECT FAQID,
                                ROW_NUMBER() OVER (
                                    ORDER BY QuestionOrder ASC, FAQID ASC
                                ) AS NewQuestionOrder
                            FROM FAQ
                            WHERE FAQCategoryID=%(category_id)s
                        ) AS ordered_faq
                            ON ordered_faq.FAQID=faq.FAQID
                        SET faq.QuestionOrder=ordered_faq.NewQuestionOrder
                        WHERE faq.FAQCategoryID=%(category_id)s"""
        data = {"category_id": category_id}
        return db_update(sql, data)
