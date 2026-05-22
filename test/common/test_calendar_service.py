"""
Unit tests for common.calendar_service helpers.
"""

from datetime import datetime

from common import calendar_service


def test_add_note_inserts_calendar_note_with_title_and_timestamp(monkeypatch):
    """
    Test that add_note stores the title and timestamp when a calendar date is provided.
    """
    calls = []

    def fake_db_insert(sql, data):
        calls.append((sql, data))
        return 17

    monkeypatch.setattr(calendar_service, "db_insert", fake_db_insert)

    result = calendar_service.CalendarService().add_note(
        note="Call venue",
        external_event_id=12,
        calendar_date="2026-05-01",
        note_title="Reminder",
    )

    assert result == 17
    assert "%(noteTitle)s, %(noteTimestamp)s" in calls[0][0]
    assert calls[0][1] == {
        "externalEventId": 12,
        "note": "Call venue",
        "noteTitle": "Reminder",
        "noteTimestamp": "2026-05-01",
    }


def test_add_note_inserts_event_note_without_calendar_fields(monkeypatch):
    """
    Test that add_note uses the current timestamp path when no calendar date is provided.
    """
    calls = []

    def fake_db_insert(sql, data):
        calls.append((sql, data))
        return 23

    monkeypatch.setattr(calendar_service, "db_insert", fake_db_insert)

    result = calendar_service.CalendarService().add_note(
        note="Doors moved",
        external_event_id=None,
    )

    assert result == 23
    assert "NULL, CURRENT_TIMESTAMP" in calls[0][0]
    assert calls[0][1] == {
        "externalEventId": None,
        "note": "Doors moved",
    }


def test_edit_note_updates_all_editable_fields(monkeypatch):
    """
    Test that edit_note sends the expected update payload to the database.
    """
    calls = []

    def fake_db_update(sql, data):
        calls.append((sql, data))
        return True

    monkeypatch.setattr(calendar_service, "db_update", fake_db_update)

    success = calendar_service.CalendarService().edit_note(
        note_id=9,
        note="Updated note",
        note_date="2026-05-02",
        note_title="Updated title",
        is_completed=True,
    )

    assert success is True
    assert "UPDATE EventNotes" in calls[0][0]
    assert calls[0][1] == {
        "note": "Updated note",
        "noteTitle": "Updated title",
        "noteId": 9,
        "noteDate": "2026-05-02",
        "isCompleted": 1,
    }


def test_delete_note_removes_note_by_id(monkeypatch):
    """
    Test that delete_note deletes the requested event note id.
    """
    calls = []

    def fake_db_delete(sql, data):
        calls.append((sql, data))
        return True

    monkeypatch.setattr(calendar_service, "db_delete", fake_db_delete)

    success = calendar_service.CalendarService().delete_note(15)

    assert success is True
    assert "DELETE FROM EventNotes" in calls[0][0]
    assert calls[0][1] == {"noteId": 15}


def test_get_calendar_notes_queries_date_range_and_maps_rows(monkeypatch):
    """
    Test that get_calendar_notes formats the date range and maps rows to Note objects.
    """
    calls = []

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        return [
            {
                "EventNoteId": "4",
                "Note": "Calendar note",
                "NoteTimestamp": "2026-05-01",
                "NoteTitle": "Reminder",
                "IsCompleted": 1,
            },
            {
                "EventNoteId": "5",
                "Note": "Second note",
                "NoteTimestamp": "2026-05-02",
                "NoteTitle": None,
                "IsCompleted": 0,
            },
        ]

    monkeypatch.setattr(calendar_service, "db_query_all", fake_db_query_all)
    start_timestamp = int(datetime(2025, 5, 1, 12, 0, 0).timestamp())
    end_timestamp = int(datetime(2025, 5, 2, 12, 0, 0).timestamp())

    notes = calendar_service.CalendarService().get_calendar_notes(
        start=start_timestamp,
        end=end_timestamp,
    )

    assert calls[0][1] == {
        "startDate": "2025-05-01",
        "endDate": "2025-05-02",
    }
    assert len(notes) == 2
    assert notes[0].note_id == 4
    assert notes[0].note == "Calendar note"
    assert notes[0].note_timestamp == "2026-05-01"
    assert notes[0].note_title == "Reminder"
    assert notes[0].is_completed is True
    assert notes[1].note_id == 5
    assert notes[1].note_title is None
    assert notes[1].is_completed is False


def test_get_calendar_notes_returns_empty_list_when_no_rows_exist(monkeypatch):
    """
    Test that get_calendar_notes returns an empty list when the query has no results.
    """
    monkeypatch.setattr(calendar_service, "db_query_all", lambda sql, data: [])

    notes = calendar_service.CalendarService().get_calendar_notes(
        start=1746057600,
        end=1746144000,
    )

    assert not notes


def test_get_event_notes_maps_rows_for_external_event(monkeypatch):
    """
    Test that get_event_notes maps rows and includes the requested external event id.
    """
    calls = []

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        return [
            {
                "EventNoteId": "7",
                "Note": "Bring guest list",
                "NoteTimestamp": "2026-05-01 10:30:00",
            }
        ]

    monkeypatch.setattr(calendar_service, "db_query_all", fake_db_query_all)

    notes = calendar_service.CalendarService().get_event_notes(33)

    assert calls[0][1] == {"externalEventId": 33}
    assert len(notes) == 1
    assert notes[0].note_id == 7
    assert notes[0].external_event_id == 33
    assert notes[0].note == "Bring guest list"
    assert notes[0].note_timestamp == "2026-05-01 10:30:00"


def test_get_event_notes_returns_empty_list_when_no_rows_exist(monkeypatch):
    """
    Test that get_event_notes returns an empty list when the query has no results.
    """
    monkeypatch.setattr(calendar_service, "db_query_all", lambda sql, data: [])

    notes = calendar_service.CalendarService().get_event_notes(33)

    assert not notes
