"""Identify older successful payments without resolved payment fee rows."""

from common.db import db_query_all
from common.stripe_financial_service import json_row
from common.stripe_payment_intent_service import EDITABLE_FIELDS


class StripeFeeReconciliationService:
    """Missing matches are unknown fees, never zero-fee confirmations."""

    def get_missing(self, start, end, days=7, limit=100, offset=0):
        """Return counts and a stable page; end is exclusive and dates are UTC."""
        data = {"start": start, "end": end, "days": days,
                "limit": limit, "offset": offset}
        source = """ FROM StripePaymentIntents pi
            WHERE pi.Status='succeeded' AND pi.DateReceived >= %(start)s
                AND pi.DateReceived < %(end)s
                AND pi.DateReceived < UTC_TIMESTAMP() - INTERVAL %(days)s DAY
                AND NOT EXISTS (SELECT 1 FROM StripeFees f
                    WHERE f.PaymentIntentId=pi.PaymentIntentId
                        AND f.IncurredByType IN ('payment_intent', 'charge'))"""
        total = db_query_all("SELECT COUNT(*) AS total" + source, data)[0]["total"]
        columns = ", ".join("pi." + field for field in
                            ["StripePaymentIntentId", *sorted(EDITABLE_FIELDS)])
        rows = db_query_all("SELECT " + columns + source +
            " ORDER BY pi.DateReceived, pi.StripePaymentIntentId LIMIT %(limit)s OFFSET %(offset)s",
            data)
        return {"total": total, "limit": limit, "offset": offset,
                "payments": [json_row(row) for row in rows]}
