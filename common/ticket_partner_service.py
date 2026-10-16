"""Resolve application partner IDs without confusing them with provider IDs."""

from common.db import db_insert, db_query_one, db_update


class TicketPartnerService:
    """Maintain the event/order/ticket identity chain used by integrations."""

    def ensure_event(self, event_id, partner_id, provider_event_id=None, cnx=None):
        data = {"event": event_id, "partner": partner_id, "provider": provider_event_id}
        row = db_query_one("""SELECT TicketPartnerEventId FROM TicketPartnerEvents
            WHERE EventId=%(event)s AND TicketPartnerId=%(partner)s
              AND PartnerEventId <=> %(provider)s""", data, cnx)
        if row:
            return int(row["TicketPartnerEventId"])
        return db_insert("""INSERT INTO TicketPartnerEvents
            (EventId, TicketPartnerId, PartnerEventId)
            VALUES (%(event)s, %(partner)s, %(provider)s)""", data, cnx)

    def ensure_imported_event(self, provider_event_id, event_data, event, cnx=None):
        """Ensure an imported TicketSocket event has an Events row and partner mapping."""
        data = {"provider": provider_event_id}
        sql = """SELECT DISTINCT EventId, EventDate FROM EventDetails
            WHERE TicketPartnerId=2 AND TicketSocketEventId=%(provider)s"""
        row = db_query_one(sql, data, cnx)
        if not row:
            # EventService owns the application's event defaults and venue lookup.
            from common.event_service import EventService  # pylint: disable=import-outside-toplevel
            payload = dict(event_data, id=provider_event_id, seller_id=event.seller_id)
            if not EventService().add_to_events(payload, event, cnx):
                return 0
            row = db_query_one(sql, data, cnx)
            if not row:
                return 0
        # Retain refresh's existing behavior of synchronizing the application date.
        if str(row["EventDate"]) != str(event.event_date):
            if not db_update("""UPDATE Events SET EventDate=%(date)s,
                LastUpdate=CURRENT_TIMESTAMP WHERE EventId=%(event)s""",
                {"date": event.event_date, "event": int(row["EventId"])}, cnx):
                return 0
        return self.ensure_event(int(row["EventId"]), 2, provider_event_id, cnx)

    def ensure_order(self, provider_event_id, provider_order_id, cnx=None):
        data = {"event": provider_event_id, "order": provider_order_id}
        row = db_query_one("""SELECT TicketPartnerEventId FROM TicketPartnerEvents
            WHERE TicketPartnerId=2 AND PartnerEventId=%(event)s""", data, cnx)
        if not row:
            return 0
        data["event"] = int(row["TicketPartnerEventId"])
        row = db_query_one("""SELECT TicketPartnerOrderId FROM TicketPartnerOrders
            WHERE TicketPartnerEventId=%(event)s AND PartnerOrderId=%(order)s""", data, cnx)
        if row:
            return int(row["TicketPartnerOrderId"])
        return db_insert("""INSERT INTO TicketPartnerOrders
            (TicketPartnerEventId, PartnerOrderId) VALUES (%(event)s, %(order)s)""", data, cnx)

    def ensure_ticket(self, order_id, provider_ticket_id, cnx=None):
        data = {"order": order_id, "ticket": provider_ticket_id}
        row = db_query_one("""SELECT TicketPartnerTicketId FROM TicketPartnerOrderTickets
            WHERE TicketPartnerOrderId=%(order)s AND PartnerTicketId=%(ticket)s""", data, cnx)
        if row:
            return int(row["TicketPartnerTicketId"])
        return db_insert("""INSERT INTO TicketPartnerOrderTickets
            (TicketPartnerOrderId, PartnerTicketId) VALUES (%(order)s, %(ticket)s)
            """, data, cnx)

    def ensure_ticket_type(self, provider_event_id, provider_type_id, cnx=None):
        """Create the mapping before reading an imported type through its view."""
        data = {"event": provider_event_id, "type": provider_type_id}
        event = db_query_one("""SELECT DISTINCT TicketPartnerEventId FROM EventDetails
            WHERE TicketSocketEventId=%(event)s AND TicketPartnerId=2""", data, cnx)
        if not event:
            return 0
        data["event"] = int(event["TicketPartnerEventId"])
        row = db_query_one("""SELECT PartnerTicketTypeId FROM PartnerTicketTypes
            WHERE TicketPartnerEventId=%(event)s AND ProviderTicketTypeId=%(type)s""", data, cnx)
        if row:
            return int(row["PartnerTicketTypeId"])
        return db_insert("""INSERT INTO PartnerTicketTypes
            (TicketPartnerEventId, ProviderTicketTypeId) VALUES (%(event)s, %(type)s)""", data, cnx)

    def socket_event(self, partner_event_id):
        row = db_query_one("""SELECT DISTINCT TicketSocketEventId FROM EventDetails
            WHERE TicketPartnerEventId=%(id)s AND TicketPartnerId=2""", {"id": partner_event_id})
        return int(row["TicketSocketEventId"]) if row and row["TicketSocketEventId"] is not None else None

    def socket_order(self, partner_order_id):
        row = db_query_one("""SELECT DISTINCT TicketSocketOrderId FROM OrderDetails
            WHERE TicketPartnerOrderId=%(id)s AND TicketPartnerId=2""", {"id": partner_order_id})
        return int(row["TicketSocketOrderId"]) if row and row["TicketSocketOrderId"] is not None else None

    def socket_ticket(self, partner_ticket_id, partner_order_id=None):
        data = {"id": partner_ticket_id}
        sql = """SELECT TicketSocketOrderTicketId FROM TicketDetails
            WHERE TicketPartnerTicketId=%(id)s AND TicketPartnerId=2"""
        if partner_order_id is not None:
            sql += " AND TicketPartnerOrderId=%(order)s"
            data["order"] = partner_order_id
        row = db_query_one(sql, data)
        return int(row["TicketSocketOrderTicketId"]) if row and row["TicketSocketOrderTicketId"] is not None else None
