from .. import db

class TicketSocketCategory:
    def __init__(self, id: int, title: str):
        self.eventCategoryId = id
        self.name = title

class TicketSocketVenue:
    def __init__(self, name: str, address1: str, address2: str, city: str, state: str, postalCode: str, country: str, timezone: str):
        self.name = name
        self.address1 = address1
        self.address2 = address2
        self.city = city
        self.state = state
        self.postalCode = postalCode
        self.country = country
        self.timezone = timezone
        
class TicketSocketTicketType:
    def __init__(self, eventId: int, ticketTypeId: int, ticketTypeName: str, totalAvailable: int, isActive: bool):
        self.eventId = eventId
        self.ticketTypeId = ticketTypeId
        self.ticketTypeName = ticketTypeName
        self.totalAvailable = totalAvailable
        self.isActive = isActive

class TicketSocketTicket:
    attendeeName: str = None
    isCheckedIn: bool = False
    def __init__(self, id: int, ticketType: str, price: float, serviceFee: float, ticketTypeId: int, barcode: str, availableScans: int, purchaseLocation: str, scannedTimestamp: int):
        self.id = id
        self.ticketType = ticketType
        self.price = price
        self.serviceFee = serviceFee
        self.ticketTypeId = ticketTypeId
        self.barcode = barcode
        self.availableScans = availableScans
        self.purchaseLocation = purchaseLocation
        self.scannedTimestamp = scannedTimestamp

class TicketSocketOrder:
    eventId: int = 0
    userId: int = 0
    numTickets: int = 0
    tickets: list[TicketSocketTicket] = []
    phone: str = ''
    shirts: list[str] = []
    purchaserFirstName: str = ''
    purchaserLastName: str = ''
    purchaserCity: str = None
    purchaserState: str = None
    purchaserZipCode: str = None
    purchaserCountry: str = None
    purchaseDate: str = ''
    purchaseTimestamp: str = ''
    email: str = ''
    attendeeNames: list[str] = []
    revenue: float = 0
    serviceFees: float = 0
    cancelled: bool = False
    deleted: bool = False

    def __init__(self, id: int, eventId: int):
        self.id = id
        self.eventId = eventId

class TicketSocketEvent:
    venue: TicketSocketVenue = None
    orders: list[TicketSocketOrder] = []
    eventCategoryId: int = 0
    utcTime: int = 0
    eventDate: str = ''
    displayDate: str = ''
    onSale: bool = True
    thumbnail: str = ''
    ticketSocketUrl: str = ''
    ticketTypes: list[TicketSocketTicketType] = []

    def __init__(self, id: int, title: str):
        self.id = id
        self.title = title


