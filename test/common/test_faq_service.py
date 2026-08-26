"""
Unit tests for common.faq_service helpers.
"""

from common import faq_service
from common.models.admin import Faq, FaqCategory


def create_category(category_id=1, name="General"):
    """
    Create a FaqCategory instance for tests.
    """
    category = FaqCategory()
    category.category_id = category_id
    category.category_name = name
    return category


def create_faq(
    faq_id=0,
    category_id=1,
    category_name="General",
    order=1,
    question="What is this?",
    answer="<p>An answer</p>",
):
    """
    Create a Faq instance for tests.
    """
    faq = Faq()
    faq.faq_id = faq_id
    faq.category = create_category(category_id, category_name)
    faq.order = order
    faq.question = question
    faq.answer = answer
    return faq


def test_get_faq_by_category_id_filters_by_category(monkeypatch):
    """
    Test that get_faq_by_category_id applies the category filter and maps rows.
    """
    calls = []
    monkeypatch.setattr(
        faq_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [
            {
                "FAQID": 7,
                "FAQCategoryID": 2,
                "CategoryName": "Billing",
                "QuestionOrder": 3,
                "QuestionText": "How much?",
                "AnswerHTML": "<p>It depends</p>",
            }
        ],
    )

    faqs = faq_service.FaqService().get_faq_by_category_id(2)

    assert len(faqs) == 1
    assert faqs[0].faq_id == 7
    assert faqs[0].category.category_id == 2
    assert faqs[0].category.category_name == "Billing"
    assert faqs[0].order == 3
    assert faqs[0].question == "How much?"
    assert faqs[0].answer == "<p>It depends</p>"
    assert "WHERE FAQ.FAQCategoryID=%(category_id)s" in calls[0][0]
    assert calls[0][1] == {"category_id": 2}


def test_get_faq_by_category_id_returns_all_categories_when_id_is_not_positive(
    monkeypatch,
):
    """
    Test that get_faq_by_category_id returns all FAQ rows when no category filter is used.
    """
    calls = []
    monkeypatch.setattr(
        faq_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    faqs = faq_service.FaqService().get_faq_by_category_id(0)

    assert not faqs
    assert "WHERE FAQ.FAQCategoryID=%(category_id)s" not in calls[0][0]
    assert "ORDER BY FAQ.FAQCategoryID ASC, FAQ.QuestionOrder ASC" in calls[0][0]
    assert calls[0][1] == {}


def test_update_faq_updates_existing_faq(monkeypatch):
    """
    Test that update_faq persists existing FAQ rows with the current order.
    """
    calls = []
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = faq_service.FaqService().update_faq(create_faq(faq_id=9, order=4))

    assert success is True
    assert "UPDATE FAQ SET" in calls[0][0]
    assert calls[0][1] == {
        "category_id": 1,
        "question": "What is this?",
        "answer": "<p>An answer</p>",
        "faq_id": 9,
        "order": 4,
    }


def test_update_faq_inserts_new_faq_after_last_question(monkeypatch):
    """
    Test that update_faq inserts new FAQ rows after the last existing question number.
    """
    insert_calls = []
    monkeypatch.setattr(
        faq_service.FaqService,
        "get_last_question_number",
        lambda self, category_id: 5,
    )
    monkeypatch.setattr(
        faq_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 44,
    )

    success = faq_service.FaqService().update_faq(create_faq(faq_id=0))

    assert success is True
    assert "INSERT INTO FAQ" in insert_calls[0][0]
    assert insert_calls[0][1] == {
        "category_id": 1,
        "question": "What is this?",
        "answer": "<p>An answer</p>",
        "order": 6,
    }


def test_update_faq_returns_false_when_new_category_has_no_last_number(monkeypatch):
    """
    Test that update_faq returns False when a new FAQ has no valid last question number.
    """
    monkeypatch.setattr(
        faq_service.FaqService,
        "get_last_question_number",
        lambda self, category_id: 0,
    )

    success = faq_service.FaqService().update_faq(create_faq(faq_id=0))

    assert success is False


def test_get_last_question_number_reads_max_order(monkeypatch):
    """
    Test that get_last_question_number returns the stored max order.
    """
    calls = []
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: calls.append((sql, data)) or {"LastNumber": 8},
    )

    last_number = faq_service.FaqService().get_last_question_number(3)

    assert last_number == 8
    assert calls[0][1] == {"category_id": 3}


def test_get_last_question_number_returns_zero_when_no_row_exists(monkeypatch):
    """
    Test that get_last_question_number falls back to zero when there is no row.
    """
    monkeypatch.setattr(faq_service, "db_query_one", lambda sql, data: {})

    last_number = faq_service.FaqService().get_last_question_number(3)

    assert last_number == 0


def test_delete_faq_passes_faq_id_to_delete(monkeypatch):
    """
    Test that delete_faq deletes the requested FAQ id.
    """
    calls = []
    monkeypatch.setattr(
        faq_service,
        "db_delete",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = faq_service.FaqService().delete_faq(12)

    assert success is True
    assert calls[0][1] == {"faq_id": 12}


def test_get_faq_categories_maps_rows(monkeypatch):
    """
    Test that get_faq_categories maps FAQ category rows into objects.
    """
    monkeypatch.setattr(
        faq_service,
        "db_query_all",
        lambda sql: [
            {"FAQCategoryID": 1, "CategoryName": "General"},
            {"FAQCategoryID": 2, "CategoryName": "Billing"},
        ],
    )

    categories = faq_service.FaqService().get_faq_categories()

    assert [category.category_id for category in categories] == [1, 2]
    assert [category.category_name for category in categories] == [
        "General",
        "Billing",
    ]


def test_move_down_swaps_with_the_next_faq(monkeypatch):
    """
    Test that move_down swaps the FAQ order with the next item in the category.
    """
    query_calls = []
    update_calls = []
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 2},
            {"FAQID": 11},
        ]
    )
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: query_calls.append((sql, data)) or next(responses),
    )
    monkeypatch.setattr(
        faq_service.FaqService,
        "get_last_question_number",
        lambda self, category_id: 5,
    )
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = faq_service.FaqService().move_down(9)

    assert success is True
    assert query_calls[0][1] == {"faq_id": 9}
    assert query_calls[1][1] == {"category_id": 4, "new_number": 3}
    assert update_calls[0][1] == {"new_number": 3, "faq_id": 9}
    assert update_calls[1][1] == {"order": 2, "existing_id": 11}


def test_move_down_returns_false_when_faq_is_already_last(monkeypatch):
    """
    Test that move_down returns False when the FAQ is already at the bottom.
    """
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: {"FAQCategoryID": 4, "QuestionOrder": 5},
    )
    monkeypatch.setattr(
        faq_service.FaqService,
        "get_last_question_number",
        lambda self, category_id: 5,
    )

    success = faq_service.FaqService().move_down(9)

    assert success is False


def test_move_down_returns_false_when_faq_row_is_missing(monkeypatch):
    """
    Test that move_down returns False when the FAQ cannot be found.
    """
    monkeypatch.setattr(faq_service, "db_query_one", lambda sql, data: None)

    success = faq_service.FaqService().move_down(9)

    assert success is False


def test_move_down_returns_false_when_category_or_order_is_invalid(monkeypatch):
    """
    Test that move_down returns False when the current FAQ position is invalid.
    """
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: {"FAQCategoryID": 0, "QuestionOrder": 0},
    )

    success = faq_service.FaqService().move_down(9)

    assert success is False


def test_move_down_returns_false_when_adjacent_faq_is_missing(monkeypatch):
    """
    Test that move_down returns False when there is no FAQ to swap with.
    """
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 2},
            None,
        ]
    )
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: next(responses),
    )
    monkeypatch.setattr(
        faq_service.FaqService,
        "get_last_question_number",
        lambda self, category_id: 5,
    )

    success = faq_service.FaqService().move_down(9)

    assert success is False


def test_move_down_returns_false_when_second_update_fails(monkeypatch):
    """
    Test that move_down returns False when the swap-back update fails.
    """
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 2},
            {"FAQID": 11},
        ]
    )
    update_results = iter([True, False])
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: next(responses),
    )
    monkeypatch.setattr(
        faq_service.FaqService,
        "get_last_question_number",
        lambda self, category_id: 5,
    )
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: next(update_results),
    )

    success = faq_service.FaqService().move_down(9)

    assert success is False


def test_move_down_returns_false_when_first_update_fails(monkeypatch):
    """
    Test that move_down returns False when the first swap update fails.
    """
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 2},
            {"FAQID": 11},
        ]
    )
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: next(responses),
    )
    monkeypatch.setattr(
        faq_service.FaqService,
        "get_last_question_number",
        lambda self, category_id: 5,
    )
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: False,
    )

    success = faq_service.FaqService().move_down(9)

    assert success is False


def test_move_up_swaps_with_the_previous_faq(monkeypatch):
    """
    Test that move_up swaps the FAQ order with the previous item in the category.
    """
    query_calls = []
    update_calls = []
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 3},
            {"FAQID": 8},
        ]
    )
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: query_calls.append((sql, data)) or next(responses),
    )
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = faq_service.FaqService().move_up(9)

    assert success is True
    assert query_calls[0][1] == {"faq_id": 9}
    assert query_calls[1][1] == {"category_id": 4, "new_number": 2}
    assert update_calls[0][1] == {"new_number": 2, "faq_id": 9}
    assert update_calls[1][1] == {"order": 3, "existing_id": 8}


def test_move_up_returns_false_when_faq_is_already_first(monkeypatch):
    """
    Test that move_up returns False when the FAQ is already at the top.
    """
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: {"FAQCategoryID": 4, "QuestionOrder": 1},
    )

    success = faq_service.FaqService().move_up(9)

    assert success is False


def test_move_up_returns_false_when_faq_row_is_missing(monkeypatch):
    """
    Test that move_up returns False when the FAQ cannot be found.
    """
    monkeypatch.setattr(faq_service, "db_query_one", lambda sql, data: None)

    success = faq_service.FaqService().move_up(9)

    assert success is False


def test_move_up_returns_false_when_category_or_order_is_invalid(monkeypatch):
    """
    Test that move_up returns False when the current FAQ position is invalid.
    """
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: {"FAQCategoryID": 0, "QuestionOrder": 0},
    )

    success = faq_service.FaqService().move_up(9)

    assert success is False


def test_move_up_returns_false_when_adjacent_faq_is_missing(monkeypatch):
    """
    Test that move_up returns False when there is no FAQ to swap with.
    """
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 3},
            None,
        ]
    )
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: next(responses),
    )

    success = faq_service.FaqService().move_up(9)

    assert success is False


def test_move_up_returns_false_when_second_update_fails(monkeypatch):
    """
    Test that move_up returns False when the swap-back update fails.
    """
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 3},
            {"FAQID": 8},
        ]
    )
    update_results = iter([True, False])
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: next(responses),
    )
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: next(update_results),
    )

    success = faq_service.FaqService().move_up(9)

    assert success is False


def test_move_up_returns_false_when_first_update_fails(monkeypatch):
    """
    Test that move_up returns False when the first swap update fails.
    """
    responses = iter(
        [
            {"FAQCategoryID": 4, "QuestionOrder": 3},
            {"FAQID": 8},
        ]
    )
    monkeypatch.setattr(
        faq_service,
        "db_query_one",
        lambda sql, data: next(responses),
    )
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: False,
    )

    success = faq_service.FaqService().move_up(9)

    assert success is False


def test_renumber_faqs_updates_category_in_question_order(monkeypatch):
    """
    Test that renumber_faqs performs the renumbering in one SQL update.
    """
    calls = []
    monkeypatch.setattr(
        faq_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = faq_service.FaqService().renumber_faqs(4)

    assert success is True
    assert len(calls) == 1
    assert "ROW_NUMBER() OVER" in calls[0][0]
    assert "ORDER BY QuestionOrder ASC, FAQID ASC" in calls[0][0]
    assert "SET faq.QuestionOrder=ordered_faq.NewQuestionOrder" in calls[0][0]
    assert calls[0][1] == {"category_id": 4}
