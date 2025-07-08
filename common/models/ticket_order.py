"""
Models for ticket orders
"""

from common.models.national_acts import VipEvent


class TicketOrderPriceLevel:
    """
    Price level data for tickets
    """

    ticket_order_price_level_id: int
    level_id: int
    level_name: str
    quantity: int
    price: float
    per_ticket_charge: float


class TicketOrderAgeLimit:
    """
    Age limit for show
    """

    age_limit_id: int
    age_limit_name: str


class TicketOrder:
    """
    Ticket order data
    """

    order_id: int
    order_date: str
    event: VipEvent
    age_limit: TicketOrderAgeLimit
    price_levels: list[TicketOrderPriceLevel] = []
    is_hologram: bool = False
    shipping_name: str
    shipping_address: str
    shipping_city: str
    shipping_state: str
    shipping_zip: str
    shipping_country: str
    contact_name: str
    contact_email: str
    contact_cc_emails: list[str] = []
    contact_phone: str
    ticket_note: str = None
    order_note: str = None
    is_fulfulled: bool = False
    is_paid: bool = False
    ship_date: str = None
    paid_date: str = None
    notes: str = None

    # computed properties
    total_tickets: int
    charged_per_ticket: float = 0
    charged_shipping: float = 0
