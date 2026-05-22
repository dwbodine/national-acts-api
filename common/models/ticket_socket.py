"""
TicketSocket models
"""


class TicketSocketCategory:
    """
    "Category" in TicketSocket API which corresponds to
    SellerEventCategory.EventCategoryId in our database
    """

    def __init__(self, event_category_id: int, title: str):
        self.event_category_id = event_category_id
        self.name = title


class TicketSocketAccount:
    """
    Model representation of data for a TS account
    """

    ticket_socket_id: int = 0
    name: str = None
    service_url: str = None
    utc_offset_hours: int = 0
    exchange_rate_id: int = 1
    exchange_rate_slug: str = None
    currency_symbol: str = None
    categories: list[TicketSocketCategory] = []


class Timezone:
    """
    Model representation of timezone for drop-downs
    """

    timezone: str
    display_name: str


class Country:
    """
    Model representation of Country data
    """

    timezones: list[Timezone] = []

    def __init__(self, country_id: int, country_name: str, country_code: str):
        self.country_id = country_id
        self.country_name = country_name
        self.country_code = country_code


class TicketSocketVenue:
    """
    Venue in TicketSocket API
    """

    def __init__(
        self,
        name: str,
        address1: str,
        city: str,
        state: str,
        postal_code: str,
        country: Country,
        timezone: str,
    ):
        self.name = name
        self.address1 = address1
        self.city = city
        self.state = state
        self.postal_code = postal_code
        self.country = country
        self.timezone = timezone


class TicketSocketTicketType:
    """
    VIP ticket type in TicketSocket API
    """

    def __init__(
        self,
        event_id: int,
        ticket_type_id: int,
        ticket_type_name: str,
        total_available: int,
        is_active: bool,
        ticket_type_order: int,
    ):
        self.event_id = event_id
        self.ticket_type_id = ticket_type_id
        self.ticket_type_name = ticket_type_name
        self.total_available = total_available
        self.is_active = is_active
        self.ticket_type_order = ticket_type_order


class TicketSocketTicket:
    """
    Ticket object in TicketSocket API
    """

    ticket_id: int = 0
    ticket_type: str = None
    price: float = 0
    service_fee: float = 0
    ticket_type_id: int = 0
    barcode: str = None
    available_scans: int = 0
    purchase_location: str = None
    scanned_timestamp: int = 0
    attendee_first_name: str = None
    attendee_last_name: str = None
    shirt_size: str = None


class TicketSocketOrder:
    """
    Order object from TicketSocket API
    """

    order_id: int = 0
    event_id: int = 0
    user_id: int = 0
    tickets: list[TicketSocketTicket] = []
    phone: str = None
    purchaser_first_name: str = None
    purchaser_last_name: str = None
    purchaser_city: str = None
    purchaser_state: str = None
    purchaser_zip_code: str = None
    purchaser_country: str = None
    purchaser_ip_address: str = None
    purchase_date: str = None
    purchase_timestamp: str = None
    purchase_unix_timestamp: int = 0
    email: str = None
    cancelled: bool = False
    deleted: bool = False


class TicketSocketEvent:
    """
    Event object from TicketSocket API
    """

    event_id: int = 0
    title: str = None
    event_date: str = None
    thumbnail: str = None
    ticket_socket_url: str = None

    event_category_id: int = 0

    orders: list[TicketSocketOrder] = []
    ticket_types: list[TicketSocketTicketType] = []
    venue: TicketSocketVenue = None
