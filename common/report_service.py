"""
Report Service
"""

from common.db import (
    db_query_all,
)
from common.models.national_acts import VipEvent
from common.models.ticket_socket import TicketSocketVenue
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class ReportService:
    """
    Service to handle all report-related activity
    """

    def get_missing_venue_events(self):
        """
        Gets events with missing venue data
        """
        events: list[VipEvent] = []
        sql = """SELECT ExternalEvents.EventID,
                ExternalEvents.Title,
                ExternalEvents.EventDate,
                TicketSocketEvents.Venue,
                TicketSocketEvents.Address,
                TicketSocketEvents.City,
                TicketSocketEvents.State,
                TicketSocketEvents.Zip,
                TicketSocketEvents.Country
            FROM ExternalEvents
            JOIN TicketSocketEvents
                ON TicketSocketEvents.Id =
                    ExternalEvents.TicketSocketEventId
            WHERE ExternalEvents.ExternalEventVenueId IS NULL
            ORDER BY ExternalEvents.EventDate DESC"""

        rows = db_query_all(sql)
        for row in rows:
            event = VipEvent()
            event.external_event_id = get_override_int_value_or_default(row["EventID"])
            event.title = get_override_string_value_or_default(row["Title"])
            event.event_date = get_override_string_value_or_default(row["EventDate"])
            venue_name = get_override_string_value_or_default(row["Venue"])
            address = get_override_string_value_or_default(row["Address"])
            city = get_override_string_value_or_default(row["City"])
            state = get_override_string_value_or_default(row["State"])
            postal_code = get_override_string_value_or_default(row["Zip"])
            country_name = get_override_string_value_or_default(row["Country"])

            venue = TicketSocketVenue(
                venue_name, address, city, state, postal_code, country_name, ""
            )
            event.venue = venue
            events.append(event)

        return events
