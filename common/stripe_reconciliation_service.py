"""Internal reconciliation of eligible orders without linked successful payments."""

from common.db import db_query_all
from common.stripe_financial_service import json_row

ELIGIBLE_EVENTS_SQL = """COALESCE(ev.ExcludeFromDashboard, 0) <> 1
    AND COALESCE(ev.IsDeleted, 0) <> 1
    AND COALESCE(ev.IsCancelled, 0) <> 1"""


class StripeReconciliationService:
    """Provide paged missing-order details and complete monthly coverage counts."""

    def get_missing_payments(self, start_date, end_date, ticket_socket_id=None,
                             limit=100, offset=0):
        """Use inclusive start/exclusive end purchase dates; null limit exports all rows."""
        data = {"start": start_date, "end": end_date}
        account_filter = ""
        if ticket_socket_id is not None:
            account_filter = " AND sec.TicketSocketId=%(account)s"
            data["account"] = ticket_socket_id
        eligible = """WITH eligible AS (
            SELECT tso.Id AS TicketSocketOrderId, tso.OrderId AS NativeOrderId,
                tso.EventId AS NativeEventId, sec.TicketSocketId, account.AccountName,
                po.TicketPartnerOrderId, ev.EventId, ev.Title AS EventTitle, ev.EventDate,
                tso.PurchaseDate, tso.IsManualTransfer,
                CONCAT_WS(' ', tso.PurchaserFirstName, tso.PurchaserLastName) AS CustomerName,
                tso.Email AS CustomerEmail, tso.CustomerProcessingFee
            FROM TicketSocketOrders tso
            JOIN TicketSocketEvents tse ON tse.Id=tso.TicketSocketEventId
            JOIN SellerEventCategory sec
                ON sec.SellerEventCategoryId=tse.SellerEventCategoryId
            JOIN TicketSocket account ON account.TicketSocketId=sec.TicketSocketId
            JOIN TicketPartnerEvents pe ON pe.TicketPartnerId=2
                AND pe.PartnerEventId=tso.TicketSocketEventId
            JOIN Events ev ON ev.EventId=pe.EventId
            LEFT JOIN TicketPartnerOrders po ON po.TicketPartnerEventId=pe.TicketPartnerEventId
                AND po.PartnerOrderId=tso.Id
            WHERE tso.PurchaseDate >= %(start)s AND tso.PurchaseDate < %(end)s
                AND tso.IsDeleted <> 1 AND tso.IsComped <> 1 AND tso.IsActive=1
                AND """ + ELIGIBLE_EVENTS_SQL + account_filter + """
        ), coverage AS (
            SELECT eligible.*, NOT EXISTS (
                SELECT 1 FROM StripePaymentIntents pi
                WHERE pi.TicketPartnerOrderId=eligible.TicketPartnerOrderId
                    AND pi.Status='succeeded'
            ) AS IsMissing FROM eligible
        ) """
        months = db_query_all(eligible + """SELECT
            DATE_FORMAT(PurchaseDate, '%Y-%m') AS Month,
            COUNT(*) AS TotalOrders, SUM(IsMissing) AS MissingPaymentIntents
            FROM coverage GROUP BY Month ORDER BY Month""", data)
        total = sum(int(row["TotalOrders"]) for row in months)
        missing = sum(int(row["MissingPaymentIntents"]) for row in months)
        for row in months:
            row["TotalOrders"] = int(row["TotalOrders"])
            row["MissingPaymentIntents"] = int(row["MissingPaymentIntents"])
            row["MissingPercentage"] = round(
                100 * row["MissingPaymentIntents"] / row["TotalOrders"], 2
            )
        query = eligible + """SELECT * FROM coverage WHERE IsMissing=1
            ORDER BY PurchaseDate, TicketSocketId, TicketSocketOrderId"""
        row_data = dict(data)
        if limit is not None:
            query += " LIMIT %(limit)s OFFSET %(offset)s"
            row_data.update(limit=limit, offset=offset)
        orders = db_query_all(query, row_data)
        return {
            "startDate": start_date.isoformat(), "endDateExclusive": end_date.isoformat(),
            "ticketSocketId": ticket_socket_id,
            "totalOrders": total, "missingPaymentIntents": missing,
            "missingPercentage": round(100 * missing / total, 2) if total else None,
            "months": months, "orders": [json_row(row) for row in orders],
            "limit": limit, "offset": offset,
        }
