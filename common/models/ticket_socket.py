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

class TicketSocketTicket:
    def __init__(self, id: int, ticketType: str, price: float):
        self.id = id
        self.ticketType = ticketType
        self.price = price    

class TicketSocketOrder:
    eventId: int = 0
    userId: int = 0
    numTickets: int = 0
    tickets: list[TicketSocketTicket] = []
    phone: str = ''
    shirts: list[str] = []
    purchaserFirstName: str = ''
    purchaserLastName: str = ''
    purchaseDate: str = ''
    email: str = ''
    attendeeNames: list[str] = []
    revenue: float = ''

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

    def __init__(self, id: int, title: str):
        self.id = id
        self.title = title

class TicketSocketRefreshHistory:
    def __init__(self, serviceEventsSkipped: list[int], eventsFailed: list[int], ordersFailed: list[int], ticketsFailed: list[int],
                  totalEventsFromService: int, eventsUpdated: int, eventsInserted: int, eventsDeactivated: int,
                  ordersInserted: int, ordersUpdated: int, ordersDeactivated: int, ticketsUpdated: int, ticketsInserted: int, ticketsDeactivated: int, 
                  startTimer: int, endTimer: int, duration: int, userId: int = 0, sellerId: int = 0, start: int = 0, end: int = 0, succeeded: bool = False,
                  errorMessage: str = None):
        self.serviceEventsSkipped = serviceEventsSkipped
        self.eventsFailed = eventsFailed
        self.ordersFailed = ordersFailed
        self.ticketsFailed = ticketsFailed
        self.totalEventsFromService = totalEventsFromService
        self.eventsUpdated = eventsUpdated
        self.eventsInserted = eventsInserted
        self.eventsDeactivated = eventsDeactivated
        self.ordersInserted = ordersInserted
        self.ordersUpdated = ordersUpdated
        self.ordersDeactivated = ordersDeactivated
        self.ticketsUpdated = ticketsUpdated
        self.ticketsInserted = ticketsInserted
        self.ticketsDeactivated = ticketsDeactivated
        self.userId = userId
        self.sellerId = sellerId
        self.start = start
        self.end = end
        self.startTimer = startTimer
        self.endTimer = endTimer
        self.duration = duration
        self.succeeded = succeeded
        self.errorMessage = errorMessage

    def commit(self):
        sql = """INSERT INTO TicketSocketRefreshHistory (UserId, SellerId, Start, End, StartTimer, EndTimer, Duration, Success, ErrorMessage, 
                 ServiceEventsSkipped,  EventsFailed, OrdersFailed, TicketsFailed, TotalEventsFromService, EventsUpdated, EventsInserted, EventsDeactivated, 
                 OrdersInserted, OrdersUpdated, OrdersDeactivated, TicketsUpdated, TicketsInserted, TicketsDeactivated) VALUES (%(userId)s, %(sellerId)s, 
                 %(start)s, %(end)s, %(startTimer)s, %(endTimer)s, %(duration)s, %(success)s, %(errorMessage)s, %(serviceEventsSkipped)s, %(eventsFailed)s, 
                 %(ordersFailed)s, %(ticketsFailed)s, %(totalEventsFromService)s, %(eventsUpdated)s, %(eventsInserted)s, %(eventsDeactivated)s, %(ordersInserted)s, 
                 %(ordersUpdated)s, %(ordersDeactivated)s, %(ticketsUpdated)s, %(ticketsInserted)s, %(ticketsDeactivated)s)"""
        
        data = {
            'userId': self.userId,
            'sellerId': self.sellerId,
            'start': self.start,
            'end': self.end,
            'startTimer': self.startTimer,
            'endTimer': self.endTimer,
            'duration': self.duration,
            'success': 1 if self.succeeded == True else 0,
            'errorMessage': self.errorMessage,
            'serviceEventsSkipped': ", ".join(self.serviceEventsSkipped),
            'eventsFailed': ", ".join(self.eventsFailed),
            'ordersFailed': ", ".join(self.ordersFailed),
            'ticketsFailed': ", ".join(self.ticketsFailed),
            'totalEventsFromService': self.totalEventsFromService,
            'eventsUpdated': self.eventsUpdated,
            'eventsInserted': self.eventsInserted,
            'eventsDeactivated': self.eventsDeactivated,
            'ordersInserted': self.ordersInserted,
            'ordersUpdated': self.ordersUpdated,
            'ordersDeactivated': self.ordersDeactivated, 
            'ticketsUpdated': self.ticketsUpdated,
            'ticketsInserted': self.ticketsInserted, 
            'ticketsDeactivated': self.ticketsDeactivated
        }

        return (db.insert(sql, data) > 0)
