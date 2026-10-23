"""Internal order-level checkout cost reconciliation; never used by client reports."""

from datetime import datetime
from decimal import Decimal
import pytz

from common.db import db_convert_list_to_parameters, db_query_all


def amount(value):
    """Keep currency calculations decimal until serialization."""
    return Decimal(str(value or 0))


def reconcile_order(order, payments):
    """Reconcile one mapped order, preserving unknown or mismatched amounts as null."""
    currency = (order.get("Currency") or "").lower()
    paid = [row for row in payments if row["Status"] == "succeeded"]
    checkout = order.get("CustomerProcessingFee")
    cost_known = bool(paid) and all(
        (row.get("ProcessingFeeCurrency") or "").lower() == currency for row in paid
    )
    same_currency = bool(paid) and all(row["Currency"].lower() == currency for row in paid)
    actual = sum((amount(row["ProcessingFee"]) for row in paid), Decimal(0)) if cost_known else None
    insurance_known = same_currency and all(row.get("InsuranceVerified") for row in paid)
    insurance = (
        sum((amount(row["Insurance"]) for row in paid), Decimal(0)) if insurance_known else None
    )
    application_fee = (
        sum((amount(row["ApplicationFee"]) for row in paid), Decimal(0)) if same_currency else None
    )
    difference = actual - amount(checkout) if actual is not None and checkout is not None else None
    return {
        "ticketPartnerOrderId": order["TicketPartnerOrderId"],
        "orderId": order["OrderId"], "eventId": order["EventId"],
        "purchaseDate": str(order["PurchaseDate"]), "currency": currency,
        "ticketSales": str(amount(order["TicketSales"])),
        "serviceFees": str(amount(order["ServiceFees"])),
        "customerProcessingFee": str(amount(checkout)) if checkout is not None else None,
        "actualProcessingFee": str(actual) if actual is not None else None,
        "processingShortfall": str(difference) if difference is not None else None,
        "insurancePremium": str(insurance) if insurance is not None else None,
        "applicationFee": str(application_fee) if application_fee is not None else None,
        "insuranceVerified": bool(insurance_known),
        "paymentMethods": sorted({row.get("PaymentMethod") or "unknown" for row in paid}),
        "paymentIntentIds": [row["PaymentIntentId"] for row in paid],
    }


def summarize(rows):
    """Sum known values by currency; include coverage so unknown costs never look complete."""
    totals = {}
    fields = ("ticketSales", "serviceFees", "customerProcessingFee", "actualProcessingFee",
              "processingShortfall", "insurancePremium", "applicationFee")
    for row in rows:
        summary = totals.setdefault(row["currency"], {
            "orders": 0, **{field: Decimal(0) for field in fields},
            "missingCustomerFee": 0, "missingStripeCost": 0, "unverifiedInsurance": 0,
            "comparedOrders": 0,
        })
        summary["orders"] += 1
        for field in fields:
            if row[field] is not None:
                summary[field] += amount(row[field])
        summary["missingCustomerFee"] += row["customerProcessingFee"] is None
        summary["missingStripeCost"] += row["actualProcessingFee"] is None
        summary["unverifiedInsurance"] += row["insurancePremium"] is None
        summary["comparedOrders"] += row["processingShortfall"] is not None
    return {currency: {key: str(value) if isinstance(value, Decimal) else value
                       for key, value in summary.items()} for currency, summary in totals.items()}


class AdminSettlementService:
    """Read TicketSocket sales and checkout fees, then bulk-load matching Stripe costs."""

    def get_report(self, start, end, seller_id=None, event_ids=None):
        """Dashboard uses purchase dates; Sales Overview scopes the selected event IDs."""
        data = {}
        if event_ids is not None:
            if not event_ids:
                return {"orders": [], "totalsByCurrency": {}, "totalOrders": 0,
                        "displayedOrders": 0}
            where = "pe.EventId IN " + db_convert_list_to_parameters(event_ids, data, "event")
        else:
            pacific = pytz.timezone("America/Los_Angeles")
            data = {"start": datetime.fromtimestamp(start, pacific).strftime("%Y-%m-%d"),
                    "end": datetime.fromtimestamp(end, pacific).strftime("%Y-%m-%d")}
            where = "tso.PurchaseDate BETWEEN %(start)s AND %(end)s"
        if seller_id:
            where += " AND ev.SellerId=%(seller)s"
            data["seller"] = seller_id
        orders = db_query_all("""SELECT po.TicketPartnerOrderId, pe.EventId,
            tso.OrderId, tso.PurchaseDate, tso.CustomerProcessingFee,
            rates.ServiceTokenId AS Currency,
            CASE WHEN tso.IsComped=1 THEN 0 ELSE COALESCE(t.TicketSales,0) END AS TicketSales,
            CASE WHEN tso.IsComped=1 THEN 0 ELSE COALESCE(t.ServiceFees,0) END AS ServiceFees
            FROM TicketPartnerOrders po
            LEFT JOIN TicketPartnerEvents pe ON pe.TicketPartnerEventId=po.TicketPartnerEventId
            LEFT JOIN Events ev ON ev.EventId=pe.EventId
            LEFT JOIN TicketSocketOrders tso ON pe.TicketPartnerId=2
                AND tso.Id=po.PartnerOrderId AND tso.TicketSocketEventId=pe.PartnerEventId
            LEFT JOIN TicketSocketEvents tse ON tse.Id=tso.TicketSocketEventId
            LEFT JOIN SellerEventCategory sec
                ON sec.SellerEventCategoryId=tse.SellerEventCategoryId
            LEFT JOIN TicketSocket account ON account.TicketSocketId=sec.TicketSocketId
            LEFT JOIN ExchangeRates rates ON rates.ExchangeRateId=account.ExchangeRateId
            LEFT JOIN (SELECT TicketSocketOrderId, SUM(Price) AS TicketSales,
                SUM(ServiceFee) AS ServiceFees FROM TicketSocketOrderTickets
                GROUP BY TicketSocketOrderId) t ON t.TicketSocketOrderId=tso.Id
            WHERE """ + where + " ORDER BY tso.PurchaseDate DESC, po.TicketPartnerOrderId DESC",
            data,
        )
        payments = []
        if orders:
            payment_data = {}
            ids = db_convert_list_to_parameters(
                [row["TicketPartnerOrderId"] for row in orders], payment_data, "order"
            )
            payments = db_query_all("""SELECT TicketPartnerOrderId, PaymentIntentId,
                Status, Currency, ProcessingFee, ProcessingFeeCurrency, Insurance,
                InsuranceVerified, ApplicationFee, PaymentMethod
                FROM StripePaymentIntents WHERE TicketPartnerOrderId IN """ + ids, payment_data)
        by_order = {}
        for payment in payments:
            by_order.setdefault(payment["TicketPartnerOrderId"], []).append(payment)
        rows = [
            reconcile_order(order, by_order.get(order["TicketPartnerOrderId"], []))
            for order in orders
        ]
        return {"orders": rows[:100], "totalsByCurrency": summarize(rows),
                "totalOrders": len(rows), "displayedOrders": min(100, len(rows))}
