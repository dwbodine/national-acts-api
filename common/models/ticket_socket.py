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


class TicketSocketVenue:
    """
    Venue in TicketSocket API
    """
    def __init__(
        self,
        name: str,
        address1: str,
        address2: str,
        city: str,
        state: str,
        postal_code: str,
        country: str,
        timezone: str,
    ):
        self.name = name
        self.address1 = address1
        self.address2 = address2
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
    ):
        self.event_id = event_id
        self.ticket_type_id = ticket_type_id
        self.ticket_type_name = ticket_type_name
        self.total_available = total_available
        self.is_active = is_active


class TicketSocketTicket:
    """
    Ticket object in TicketSocket API
    """
    def __init__(
        self,
        ticket_id: int,
        ticket_type: str,
        price: float,
        service_fee: float,
        ticket_type_id: int,
        barcode: str,
        available_scans: int,
        purchase_location: str,
        scanned_timestamp: int,
        attendee_first_name: str,
        attendee_last_name: str,
    ):
        self.ticket_id = ticket_id
        self.ticket_type = ticket_type
        self.price = price
        self.service_fee = service_fee
        self.ticket_type_id = ticket_type_id
        self.barcode = barcode
        self.available_scans = available_scans
        self.purchase_location = purchase_location
        self.scanned_timestamp = scanned_timestamp
        self.attendee_first_name = attendee_first_name
        self.attendee_last_name = attendee_last_name


class TicketSocketOrder:
    """
    Order object from TicketSocket API
    """
    event_id: int = 0
    user_id: int = 0
    num_tickets: int = 0
    tickets: list[TicketSocketTicket] = []
    phone: str = ""
    shirts: list[str] = []
    purchaser_first_name: str = ""
    purchaser_last_name: str = ""
    purchaser_city: str = None
    purchaser_state: str = None
    purchaser_zip_code: str = None
    purchaser_country: str = None
    purchaser_ip_address: str = None
    purchase_date: str = ""
    purchase_timestamp: str = ""
    email: str = ""
    revenue: float = 0
    service_fees: float = 0
    cancelled: bool = False
    deleted: bool = False

    def __init__(self, order_id: int, event_id: int):
        self.order_id = order_id
        self.event_id = event_id


class TicketSocketEvent:
    """
    Event object from TicketSocket API
    """
    venue: TicketSocketVenue = None
    orders: list[TicketSocketOrder] = []
    event_category_id: int = 0
    utc_time: int = 0
    event_date: str = ""
    display_date: str = ""
    on_sale: bool = True
    thumbnail: str = ""
    ticket_socket_url: str = ""
    ticket_types: list[TicketSocketTicketType] = []

    def __init__(self, event_id: int, title: str):
        self.event_id = event_id
        self.title = title
