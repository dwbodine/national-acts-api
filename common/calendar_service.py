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
            "note": note,
        }

        if calendar_date is not None:
            sql += """%(noteTitle)s, %(noteTimestamp)s"""
            data["noteTitle"] = note_title
            data["noteTimestamp"] = calendar_date
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
            "note": note,
            "noteTitle": note_title,
            "noteId": note_id,
            "noteDate": note_date,
            "isCompleted": 1 if is_completed is True else 0,
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
            note.note_id = int(row["EventNoteId"])
            note.note = str(row["Note"])
            note.note_timestamp = str(row["NoteTimestamp"])
            note.note_title = (
                str(row["NoteTitle"]) if row["NoteTitle"] is not None else None
            )
            note.is_completed = True if int(row["IsCompleted"]) == 1 else False
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
            note.note_id = int(row["EventNoteId"])
            note.external_event_id = external_event_id
            note.note = str(row["Note"])
            note.note_timestamp = str(row["NoteTimestamp"])
            notes.append(note)
        return notes
