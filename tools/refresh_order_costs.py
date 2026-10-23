"""Refresh authoritative TicketSocket checkout and Stripe costs for specific order IDs."""

import argparse
from decimal import Decimal
import os

from dotenv import load_dotenv
import stripe

from common.db import db_query_all, db_update
from common.models.stripe import StripeTransaction
from common.stripe_service import StripeService
from common.ticket_socket_service import TicketSocketService


def main():
    """Explicit order IDs avoid a broad historical TicketSocket refresh."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-ids", required=True, help="Comma-separated TicketSocket order numbers")
    parser.add_argument("--env-file", default="/app/.env")
    args = parser.parse_args()
    try:
        ids = list(dict.fromkeys(int(value) for value in args.order_ids.split(",")))
    except ValueError:
        parser.error("Order IDs must be comma-separated integers")
    if not ids or any(value <= 0 for value in ids):
        parser.error("Order IDs must be positive")
    load_dotenv(args.env_file, override=False)
    client = stripe.StripeClient(api_key=os.environ["STRIPE_API_SECRET_KEY"])
    service = StripeService()
    service.refresh_financials = True
    for native_id in ids:
        rows = db_query_all("""SELECT tso.Id, tso.EventId, sec.TicketSocketId
            FROM TicketSocketOrders tso
            JOIN TicketSocketEvents e ON e.Id=tso.TicketSocketEventId
            JOIN SellerEventCategory sec ON sec.SellerEventCategoryId=e.SellerEventCategoryId
            WHERE tso.OrderId=%(id)s""", {"id": native_id})
        if not rows:
            raise RuntimeError(f"Order {native_id} is not present locally")
        checkout_updates = []
        for row in rows:
            order = TicketSocketService(row["TicketSocketId"]).get_order_from_order_id(
                native_id, row["EventId"]
            )
            if order is None or order.customer_processing_fee is None:
                raise RuntimeError(f"Order {native_id} has no authoritative checkout fee")
            checkout_updates.append({"id": row["Id"], "fee": Decimal(order.customer_processing_fee)})
        payment_count = 0
        for intent in client.v1.payment_intents.search({
            "query": f"metadata['orderId']:'{native_id}'",
            "expand": ["data.latest_charge.balance_transaction"],
        }).auto_paging_iter():
            if intent.status == "succeeded":
                service._upsert_transaction(StripeTransaction(str(native_id), intent.status, intent))
                payment_count += 1
        for update in checkout_updates:
            db_update("UPDATE TicketSocketOrders SET CustomerProcessingFee=%(fee)s WHERE Id=%(id)s", update)
        print(f"Order {native_id}: refreshed checkout costs and {payment_count} successful payments")


if __name__ == "__main__":
    main()
