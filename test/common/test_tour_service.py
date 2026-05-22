"""
Unit tests for common.tour_service helpers.
"""

from datetime import datetime

from common import tour_service
from common.models.national_acts import Tour, VipEvent


class FakeDateTime(datetime):
    """
    Fixed datetime helper for tour date-filter tests.
    """

    @classmethod
    def now(cls, tz=None):
        """
        Return a fixed current datetime.
        """
        current = cls(2026, 4, 23, 12, 0, 0)
        if tz is not None:
            return tz.localize(current)
        return current


class FakeSeller:
    """
    Test double for Seller model lookups.
    """

    instances = []

    def __init__(self, seller_id):
        self.seller_id = seller_id
        FakeSeller.instances.append(self)


class FakeEventService:
    """
    Test double for event lookups used by tours.
    """

    instances = []
    events_by_event_id = {}

    def __init__(self):
        self.calls = []
        FakeEventService.instances.append(self)

    def get_events_and_orders(self, **kwargs):
        """
        Return configured events for the requested external event id.
        """
        self.calls.append(kwargs)
        event_id = kwargs.get("event_id")
        return FakeEventService.events_by_event_id.get(event_id, [])


def create_tour(
    tour_id=1,
    tour_name="Spring Tour",
    announce_date="2026-05-01",
    is_active=True,
):
    """
    Create a Tour instance for add and update tests.
    """
    tour = Tour()
    tour.tour_id = tour_id
    tour.tour_name = tour_name
    tour.announce_date = announce_date
    tour.is_active = is_active
    tour.sellers = []
    tour.events = []
    return tour


def create_event(external_event_id):
    """
    Create a VipEvent instance with an external event id.
    """
    event = VipEvent()
    event.external_event_id = external_event_id
    return event


def test_get_all_tours_maps_tours_sellers_and_events(monkeypatch):
    """
    Test that get_all_tours maps tours and loads sellers and events for each tour.
    """
    FakeSeller.instances = []
    FakeEventService.instances = []
    FakeEventService.events_by_event_id = {
        44: [create_event(44)],
        55: [],
    }
    calls = []
    monkeypatch.setattr(tour_service, "Seller", FakeSeller)
    monkeypatch.setattr(tour_service, "EventService", FakeEventService)

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        if "FROM Tour " in sql:
            return [
                {
                    "TourId": 9,
                    "TourName": "Spring Tour",
                    "IsActive": 1,
                    "AnnounceDate": "2026-05-01",
                }
            ]
        if "FROM TourSeller" in sql:
            return [{"SellerId": 100}, {"SellerId": 200}]
        return [
            {"ExternalEventId": 44},
            {"ExternalEventId": 0},
            {"ExternalEventId": 55},
        ]

    monkeypatch.setattr(tour_service, "db_query_all", fake_db_query_all)

    tours = tour_service.TourService().get_all_tours(seller_id=7)

    assert len(tours) == 1
    assert tours[0].tour_id == 9
    assert tours[0].tour_name == "Spring Tour"
    assert tours[0].is_active is True
    assert tours[0].announce_date == "2026-05-01"
    assert [seller.seller_id for seller in tours[0].sellers] == [100, 200]
    assert [event.external_event_id for event in tours[0].events] == [44]
    assert "WHERE EXISTS" in calls[0][0]
    assert "ORDER BY Tour.AnnounceDate ASC, Tour.TourName ASC" in calls[0][0]
    assert calls[0][1] == {"seller_id": 7}
    assert FakeEventService.instances[0].calls == [
        {
            "event_id": 44,
            "ignore_flags": True,
            "exclude_external": False,
            "get_orders": False,
            "is_portal": True,
        },
        {
            "event_id": 55,
            "ignore_flags": True,
            "exclude_external": False,
            "get_orders": False,
            "is_portal": True,
        },
    ]


def test_get_all_tours_skips_missing_seller_models(monkeypatch):
    """
    Test that get_all_tours skips seller rows when the seller lookup returns None.
    """
    FakeSeller.instances = []
    FakeEventService.instances = []
    FakeEventService.events_by_event_id = {}

    def fake_seller_factory(seller_id):
        """
        Return None for invalid seller ids.
        """
        if seller_id == 0:
            return None
        return FakeSeller(seller_id)

    def fake_db_query_all(sql, _data):
        if "FROM Tour " in sql:
            return [
                {
                    "TourId": 9,
                    "TourName": "Spring Tour",
                    "IsActive": 1,
                    "AnnounceDate": "2026-05-01",
                }
            ]
        if "FROM TourSeller" in sql:
            return [{"SellerId": 0}, {"SellerId": 200}]
        return []

    monkeypatch.setattr(tour_service, "Seller", fake_seller_factory)
    monkeypatch.setattr(tour_service, "EventService", FakeEventService)
    monkeypatch.setattr(tour_service, "db_query_all", fake_db_query_all)

    tours = tour_service.TourService().get_all_tours(seller_id=7)

    assert len(tours) == 1
    assert [seller.seller_id for seller in tours[0].sellers] == [200]


def test_get_all_tours_builds_between_filter_for_start_and_end(monkeypatch):
    """
    Test that get_all_tours adds an announce-date range when start and end are provided.
    """
    calls = []
    monkeypatch.setattr(
        tour_service.TourService,
        "_TourService__get_sellers_by_tour_id",
        lambda self, tour_id: [],
    )
    monkeypatch.setattr(
        tour_service.TourService,
        "_TourService__get_events_by_tour_id",
        lambda self, tour_id: [],
    )
    monkeypatch.setattr(
        tour_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    tours = tour_service.TourService().get_all_tours(
        seller_id=3,
        start=1746057600,
        end=1748736000,
    )

    assert not tours
    assert "AND Tour.AnnounceDate BETWEEN %(startDate)s AND %(endDate)s" in calls[0][0]
    assert calls[0][1] == {
        "seller_id": 3,
        "startDate": datetime.fromtimestamp(1746057600).strftime("%Y-%m-%d"),
        "endDate": datetime.fromtimestamp(1748736000).strftime("%Y-%m-%d"),
    }


def test_get_all_tours_uses_current_date_when_only_end_is_future(monkeypatch):
    """
    Test that get_all_tours uses today as the start date when only a future end is provided.
    """
    calls = []
    monkeypatch.setattr(tour_service, "datetime", FakeDateTime)
    monkeypatch.setattr(
        tour_service.TourService,
        "_TourService__get_sellers_by_tour_id",
        lambda self, tour_id: [],
    )
    monkeypatch.setattr(
        tour_service.TourService,
        "_TourService__get_events_by_tour_id",
        lambda self, tour_id: [],
    )
    monkeypatch.setattr(
        tour_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )
    future_end = int(FakeDateTime(2026, 5, 1, 0, 0, 0).timestamp())

    tours = tour_service.TourService().get_all_tours(
        seller_id=4,
        end=future_end,
    )

    assert not tours
    assert "AND Tour.AnnounceDate BETWEEN %(startDate)s AND %(endDate)s" in calls[0][0]
    assert calls[0][1] == {
        "seller_id": 4,
        "startDate": "2026-04-23",
        "endDate": datetime.fromtimestamp(future_end).strftime("%Y-%m-%d"),
    }


def test_get_all_tours_builds_start_only_filter(monkeypatch):
    """
    Test that get_all_tours adds a lower-bound filter when only start is provided.
    """
    calls = []
    monkeypatch.setattr(
        tour_service.TourService,
        "_TourService__get_sellers_by_tour_id",
        lambda self, tour_id: [],
    )
    monkeypatch.setattr(
        tour_service.TourService,
        "_TourService__get_events_by_tour_id",
        lambda self, tour_id: [],
    )
    monkeypatch.setattr(
        tour_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    tours = tour_service.TourService().get_all_tours(
        seller_id=5,
        start=1746057600,
    )

    assert not tours
    assert "AND Tour.AnnounceDate >= %(startDate)s" in calls[0][0]
    assert calls[0][1] == {
        "seller_id": 5,
        "startDate": datetime.fromtimestamp(1746057600).strftime("%Y-%m-%d"),
    }


def test_add_tour_inserts_tour_sellers_and_events(monkeypatch):
    """
    Test that add_tour inserts the tour and then syncs sellers and events.
    """
    insert_calls = []
    delete_calls = []
    monkeypatch.setattr(
        tour_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        if "INSERT INTO Tour (" in sql:
            return 12
        return len(insert_calls) + 50

    monkeypatch.setattr(tour_service, "db_insert", fake_db_insert)

    tour = create_tour(tour_id=0)
    seller_one = FakeSeller(100)
    seller_two = FakeSeller(200)
    tour.sellers = [seller_one, seller_two]
    tour.events = [create_event(44), create_event(55)]

    success = tour_service.TourService().add_tour(tour)

    assert success is True
    assert "INSERT INTO Tour (TourName, AnnounceDate)" in insert_calls[0][0]
    assert insert_calls[0][1] == {
        "tourName": "Spring Tour",
        "announceDate": "2026-05-01",
    }
    assert "DELETE FROM TourSeller" in delete_calls[0][0]
    assert delete_calls[0][1] == {"tourId": 12}
    assert insert_calls[1][1] == {"tourId": 12, "sellerId": 100}
    assert insert_calls[2][1] == {"tourId": 12, "sellerId": 200}
    assert "DELETE FROM TourEvent" in delete_calls[1][0]
    assert delete_calls[1][1] == {"tourId": 12}
    assert insert_calls[3][1] == {"tourId": 12, "externalEventId": 44}
    assert insert_calls[4][1] == {"tourId": 12, "externalEventId": 55}


def test_add_tour_returns_false_when_tour_insert_fails(monkeypatch):
    """
    Test that add_tour returns false when the tour insert fails.
    """
    monkeypatch.setattr(tour_service, "db_insert", lambda sql, data: 0)

    success = tour_service.TourService().add_tour(create_tour(tour_id=0))

    assert success is False


def test_add_tour_returns_false_when_seller_insert_fails(monkeypatch):
    """
    Test that add_tour returns false and skips event syncing when seller syncing fails.
    """
    delete_calls = []
    monkeypatch.setattr(
        tour_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    def fake_db_insert(sql, _data):
        if "INSERT INTO Tour (" in sql:
            return 12
        if "INSERT INTO TourSeller" in sql:
            return 0
        return 99

    monkeypatch.setattr(tour_service, "db_insert", fake_db_insert)

    tour = create_tour(tour_id=0)
    tour.sellers = [FakeSeller(100)]
    tour.events = [create_event(44)]

    success = tour_service.TourService().add_tour(tour)

    assert success is False
    assert len(delete_calls) == 1
    assert "DELETE FROM TourSeller" in delete_calls[0][0]


def test_add_tour_returns_false_when_event_insert_fails(monkeypatch):
    """
    Test that add_tour returns false when syncing a tour event fails.
    """
    insert_calls = []
    monkeypatch.setattr(tour_service, "db_delete", lambda sql, data: True)

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        if "INSERT INTO Tour (" in sql:
            return 12
        if "INSERT INTO TourSeller" in sql:
            return 70
        return 0

    monkeypatch.setattr(tour_service, "db_insert", fake_db_insert)

    tour = create_tour(tour_id=0)
    tour.sellers = [FakeSeller(100)]
    tour.events = [create_event(44)]

    success = tour_service.TourService().add_tour(tour)

    assert success is False
    assert "INSERT INTO TourEvent" in insert_calls[-1][0]


def test_update_tour_updates_and_syncs_related_data(monkeypatch):
    """
    Test that update_tour updates the tour and then resyncs sellers and events.
    """
    update_calls = []
    insert_calls = []
    delete_calls = []
    monkeypatch.setattr(
        tour_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        tour_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        tour_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 77,
    )

    tour = create_tour(tour_id=9, is_active=False)
    tour.sellers = [FakeSeller(100)]
    tour.events = [create_event(44)]

    success = tour_service.TourService().update_tour(tour)

    assert success is True
    assert "UPDATE Tour" in update_calls[0][0]
    assert update_calls[0][1] == {
        "tourName": "Spring Tour",
        "isActive": 0,
        "announceDate": "2026-05-01",
        "tourId": 9,
    }
    assert "DELETE FROM TourSeller" in delete_calls[0][0]
    assert insert_calls[0][1] == {"tourId": 9, "sellerId": 100}
    assert "DELETE FROM TourEvent" in delete_calls[1][0]
    assert insert_calls[1][1] == {"tourId": 9, "externalEventId": 44}


def test_update_tour_returns_false_when_update_fails(monkeypatch):
    """
    Test that update_tour returns false when the base tour update fails.
    """
    monkeypatch.setattr(tour_service, "db_update", lambda sql, data: False)

    success = tour_service.TourService().update_tour(create_tour(tour_id=9))

    assert success is False


def test_update_tour_returns_false_when_seller_sync_fails(monkeypatch):
    """
    Test that update_tour returns false and skips event syncing when seller syncing fails.
    """
    delete_calls = []
    monkeypatch.setattr(tour_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        tour_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    def fake_db_insert(sql, _data):
        if "INSERT INTO TourSeller" in sql:
            return 0
        return 99

    monkeypatch.setattr(tour_service, "db_insert", fake_db_insert)

    tour = create_tour(tour_id=9)
    tour.sellers = [FakeSeller(100)]
    tour.events = [create_event(44)]

    success = tour_service.TourService().update_tour(tour)

    assert success is False
    assert len(delete_calls) == 1
    assert "DELETE FROM TourSeller" in delete_calls[0][0]
