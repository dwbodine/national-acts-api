"""
Calendar Service
"""

from datetime import datetime

from common.db import (
    db_delete,
    db_query_all,
    db_insert,
    db_update,
)
from common.models.national_acts import Note
from common.utility import (
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
)


class CalendarService:
    """
    Service to handle calendar-related activity
    """

    def add_note(
        self,
        note: str,
        external_event_id: int = None,
        calendar_date: str = None,
        note_title: str = None,
    ):
        """
        API method to add a note specific to an event or calendar date
        """
        sql = """INSERT INTO EventNotes
                    (ExternalEventId, Note, NoteTitle, NoteTimestamp)
                    VALUES (%(externalEventId)s, %(note)s, """
        data = {
            "externalEventId": (
                external_event_id if external_event_id is not None else None
            ),
            "note": get_override_string_value_or_default(note),
        }

        if calendar_date is not None:
            sql += """%(noteTitle)s, %(noteTimestamp)s"""
            data["noteTitle"] = get_override_string_value_or_default(note_title)
            data["noteTimestamp"] = get_override_string_value_or_default(calendar_date)
        else:
            sql += """NULL, CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')"""

        sql += """)"""

        success = db_insert(sql, data)
        return success

    def edit_note(
        self,
        note_id: int,
        note: str,
        note_date: str,
        note_title: str = None,
        is_completed: bool = False,
    ):
        """
        API method to update any note from its id
        """
        sql = """UPDATE EventNotes
                    SET NoteTitle=%(noteTitle)s,
                    Note=%(note)s, 
                    IsCompleted=%(isCompleted)s, 
                    NoteTimeStamp=%(noteDate)s, 
                    LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                    WHERE EventNoteId=%(noteId)s"""
        data = {
            "note": get_override_string_value_or_default(note),
            "noteTitle": get_override_string_value_or_default(note_title),
            "noteId": get_override_int_value_or_default(note_id),
            "noteDate": get_override_string_value_or_default(note_date),
            "isCompleted": get_override_tinyint_value_or_default_from_bool(
                is_completed
            ),
        }

        success = db_update(sql, data)
        return success

    def delete_note(
        self,
        note_id: int,
    ):
        """
        API method to delete any note from its id
        """
        sql = """DELETE FROM EventNotes
                    WHERE EventNoteId=%(noteId)s"""
        data = {"noteId": note_id}

        success = db_delete(sql, data)
        return success

    def get_calendar_notes(self, start: int, end: int):
        """
        API method to fetch calendar notes
        """
        notes: list[Note] = []
        sql = """SELECT * FROM EventNotes
                    WHERE ExternalEventId IS NULL AND
                    NoteTimestamp BETWEEN %(startDate)s and %(endDate)s 
                    ORDER BY NoteTimestamp ASC, IsCompleted DESC, NoteTitle ASC"""
        data = {
            "startDate": datetime.fromtimestamp(start).strftime("%Y-%m-%d"),
            "endDate": datetime.fromtimestamp(end).strftime("%Y-%m-%d"),
        }
        rows = db_query_all(sql, data)
        for row in rows:
            note = Note()
            note.note_id = get_override_int_value_or_default(row["EventNoteId"])
            note.note = get_override_string_value_or_default(row["Note"])
            note.note_timestamp = get_override_string_value_or_default(
                row["NoteTimestamp"]
            )
            note.note_title = get_override_string_value_or_default(row["NoteTitle"])
            note.is_completed = get_override_bool_value_or_default(row["IsCompleted"])
            notes.append(note)
        return notes

    def get_event_notes(self, external_event_id: int):
        """
        API method to fetch event notes
        """
        notes: list[Note] = []
        sql = """SELECT * FROM EventNotes
                    WHERE ExternalEventId=%(externalEventId)s
                    ORDER BY NoteTimestamp DESC"""
        data = {"externalEventId": external_event_id}
        rows = db_query_all(sql, data)
        for row in rows:
            note = Note()
            note.note_id = get_override_int_value_or_default(row["EventNoteId"])
            note.external_event_id = external_event_id
            note.note = get_override_string_value_or_default(row["Note"])
            note.note_timestamp = get_override_string_value_or_default(
                row["NoteTimestamp"]
            )
            notes.append(note)
        return notes
