"""Explicit administrator edits to local Stripe payment intent records."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import mariadb

from common.db import db_get_connection
from common.stripe_financial_service import json_row
from common.stripe_reconciliation_service import ELIGIBLE_EVENTS_SQL

TEXT_FIELDS = {
    "PaymentIntentId": 100, "EventName": 100, "Description": 255,
    "CustomerName": 100, "CustomerEmail": 100, "CustomerPhone": None,
    "Currency": 3, "SourceUrl": 64, "Status": 32, "PaymentMethod": 32, "StripeAccount": 64,
    "ProcessingFeeCurrency": 3,
}
NULLABLE_TEXT = {"EventName", "CustomerName", "CustomerEmail", "CustomerPhone", "PaymentMethod",
                 "ProcessingFeeCurrency"}
DECIMAL_FIELDS = {"Total": (10, 2), "ProcessingFee": (10, 2), "ExchangeRate": (10, 6),
                  "Insurance": (18, 6), "ApplicationFee": (18, 6)}
ID_FIELDS = {"TicketPartnerOrderId", "NativeOrderId", "NativeEventId"}
REQUIRED_INSERT_FIELDS = {"PaymentIntentId", "Description", "DateReceived", "Total",
                          "ProcessingFee", "Currency", "SourceUrl", "ExchangeRate"}


class PaymentIntentConflict(ValueError):
    """A Stripe identifier is already owned by a different local record."""


def positive_id(value, field):
    """Reject coercions such as booleans/fractions and preserve signed INT bounds."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field} must be a positive integer")
    if isinstance(value, str) and not value.isascii():
        raise ValueError(f"{field} must be a positive integer")
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError(f"{field} must be a positive integer") from error
    if not 1 <= result <= 2147483647:
        raise ValueError(f"{field} must be a positive integer within INT range")
    return result


def validate_changes(payload):
    """Only bind known database fields, with schema-compatible types and precision."""
    if not isinstance(payload, dict):
        raise ValueError("A JSON object is required")
    allowed = set(TEXT_FIELDS) | set(DECIMAL_FIELDS) | ID_FIELDS | {
        "StripePaymentIntentId", "DateReceived", "InsuranceVerified",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError("Unknown fields: " + ", ".join(sorted(unknown)))
    record_id = (positive_id(payload["StripePaymentIntentId"], "StripePaymentIntentId")
                 if payload.get("StripePaymentIntentId") is not None else None)
    changes = {key: value for key, value in payload.items() if key != "StripePaymentIntentId"}
    if not changes:
        raise ValueError("Provide at least one field to insert or update")
    for field, value in changes.items():
        if field in TEXT_FIELDS:
            if value is None and field in NULLABLE_TEXT:
                continue
            maximum = TEXT_FIELDS[field]
            if not isinstance(value, str) or maximum is not None and len(value) > maximum:
                raise ValueError(f"Invalid {field}")
        elif field in ID_FIELDS:
            changes[field] = positive_id(value, field) if value is not None else None
        elif field in DECIMAL_FIELDS:
            if field == "Insurance" and value is None:
                continue
            try:
                number = Decimal(str(value))
            except InvalidOperation as error:
                raise ValueError(f"Invalid {field}") from error
            precision, scale = DECIMAL_FIELDS[field]
            if (not number.is_finite() or number < 0 or number >= 10 ** (precision - scale)
                    or number != number.quantize(Decimal(1).scaleb(-scale))):
                raise ValueError(f"Invalid precision or range for {field}")
            changes[field] = number
        elif field == "InsuranceVerified":
            if not isinstance(value, (int, bool)) or value not in (0, 1):
                raise ValueError("InsuranceVerified must be 0 or 1")
        elif field == "DateReceived":
            if not isinstance(value, str):
                raise ValueError("DateReceived must be an ISO datetime")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            changes[field] = (parsed.astimezone(timezone.utc).replace(tzinfo=None)
                              if parsed.tzinfo else parsed)
    if "PaymentIntentId" in changes and not changes["PaymentIntentId"].startswith("pi_"):
        raise ValueError("PaymentIntentId must be a Stripe pi_ identifier")
    for field in ("Currency", "ProcessingFeeCurrency"):
        if field in changes and changes[field] is not None:
            value = changes[field]
            if len(value) != 3 or not value.isascii() or not value.isalpha():
                raise ValueError(f"{field} must be a three-letter currency code")
            changes[field] = value.lower()
    if "Status" in changes and changes["Status"] != "succeeded":
        raise ValueError("Only succeeded payment intents can be stored")
    return record_id, changes


class StripePaymentIntentService:
    """Save one explicitly identified payment; ordinary imports keep their existing behavior."""

    def save(self, payload):
        """Patch the supplied local ID, or create a complete row with an automatic ID."""
        record_id, changes = validate_changes(payload)
        connection = db_get_connection()
        cursor = None
        try:
            connection.begin()
            cursor = connection.cursor(dictionary=True)
            existing = None
            if record_id is not None:
                cursor.execute("""SELECT * FROM StripePaymentIntents
                    WHERE StripePaymentIntentId=%(id)s FOR UPDATE""", {"id": record_id})
                existing = cursor.fetchone()
            if existing and "PaymentIntentId" in changes:
                if changes["PaymentIntentId"] != existing["PaymentIntentId"]:
                    raise PaymentIntentConflict(
                        "An existing row's PaymentIntentId cannot be changed"
                    )
            if not existing:
                missing = REQUIRED_INSERT_FIELDS - changes.keys()
                if missing:
                    raise ValueError("Missing insert fields: " + ", ".join(sorted(missing)))
            merged = {**(existing or {}), **changes}
            if merged.get("TicketPartnerOrderId") is not None:
                self._resolve_order(cursor, merged, changes)
            fields = list(changes)
            values = {**changes, "id": record_id}
            if existing:
                assignments = ", ".join(f"{field}=%({field})s" for field in fields)
                cursor.execute("UPDATE StripePaymentIntents SET " + assignments
                               + ", LastUpdated=CURRENT_TIMESTAMP "
                               "WHERE StripePaymentIntentId=%(id)s",
                               values)
            else:
                insert_fields = ["StripePaymentIntentId", *fields] if record_id else fields
                columns = ", ".join(insert_fields)
                placeholders = ", ".join("%(id)s" if field == "StripePaymentIntentId"
                                         else f"%({field})s" for field in insert_fields)
                cursor.execute(f"INSERT INTO StripePaymentIntents ({columns}) "
                               f"VALUES ({placeholders})", values)
                record_id = record_id or cursor.lastrowid
            cursor.execute("SELECT * FROM StripePaymentIntents WHERE StripePaymentIntentId=%(id)s",
                           {"id": record_id})
            result = cursor.fetchone()
            connection.commit()
            return {"created": not bool(existing), "paymentIntent": json_row(result)}
        except mariadb.IntegrityError as error:
            connection.rollback()
            raise PaymentIntentConflict(
                "PaymentIntentId or local ID conflicts with an existing row"
            ) from error
        except Exception:
            connection.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    @staticmethod
    def _resolve_order(cursor, merged, changes):
        """Derive native IDs from an eligible internal order; reject inconsistent edits."""
        cursor.execute("""SELECT tso.OrderId AS NativeOrderId, tso.EventId AS NativeEventId
            FROM TicketPartnerOrders po
            JOIN TicketPartnerEvents pe ON pe.TicketPartnerEventId=po.TicketPartnerEventId
                AND pe.TicketPartnerId=2
            JOIN Events ev ON ev.EventId=pe.EventId
            JOIN TicketSocketOrders tso ON tso.Id=po.PartnerOrderId
                AND tso.TicketSocketEventId=pe.PartnerEventId
            WHERE po.TicketPartnerOrderId=%(id)s AND """ + ELIGIBLE_EVENTS_SQL,
            {"id": merged["TicketPartnerOrderId"]})
        order = cursor.fetchone()
        if not order:
            raise ValueError("TicketPartnerOrderId must identify an eligible TicketSocket order")
        for field in ("NativeOrderId", "NativeEventId"):
            if field in changes and changes[field] != order[field]:
                raise ValueError(f"{field} does not match TicketPartnerOrderId")
            changes[field] = order[field]
