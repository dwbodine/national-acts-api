"""
Unit tests for common.seller_service helpers.
"""

from common import seller_service
from common.models.ticket_socket import Country


class FakeSellerModel:
    """
    Test double for Seller model lookups.
    """

    categories_by_seller_id = {}
    instances = []

    def __init__(self, seller_id):
        self.seller_id = seller_id
        self.seller_event_categories = FakeSellerModel.categories_by_seller_id.get(
            seller_id, []
        )
        FakeSellerModel.instances.append(self)


class FakeSellerEventCategory:
    """
    Test double for SellerEventCategory records used in update flows.
    """

    def __init__(
        self,
        seller_id,
        ticket_socket_id,
        event_category_id,
        seller_event_category_id=0,
        is_visible_on_site=True,
        is_visible_on_portal=True,
        seller_rate_percent=0.0,
    ):
        self.seller_id = seller_id
        self.ticket_socket_id = ticket_socket_id
        self.event_category_id = event_category_id
        self.seller_event_category_id = seller_event_category_id
        self.is_visible_on_site = is_visible_on_site
        self.is_visible_on_portal = is_visible_on_portal
        self.seller_rate_percent = seller_rate_percent

    def __eq__(self, other):
        """
        Match categories by seller and ticket-socket ids.
        """
        return (
            self.seller_id == other.seller_id
            and self.ticket_socket_id == other.ticket_socket_id
        )


class FakeSellerRecord:
    """
    Mutable seller object for update tests.
    """

    def __init__(self, seller_id=0):
        self.seller_id = seller_id
        self.name = "Seller A"
        self.seller_type = 7
        self.hide_in_list = True
        self.hide_seller_rate = False
        self.is_active = True
        self.address = "123 Main"
        self.city = "Austin"
        self.state = "TX"
        self.zip = "73301"
        self.country = Country(1, "USA", "US")
        self.phone = "555-1111"
        self.email = "seller@example.com"
        self.twitter = "@seller"
        self.facebook = "seller-fb"
        self.instagram = "@seller-ig"
        self.youtube = "seller-yt"
        self.spotify = "seller-sp"
        self.website = "https://seller.example.com"
        self.website_display_text = "Seller Site"
        self.seller_event_categories = []


def test_get_user_sellers_returns_empty_for_invalid_or_missing_users(monkeypatch):
    """
    Test that get_user_sellers returns an empty list for invalid or missing users.
    """
    monkeypatch.setattr(
        seller_service,
        "db_query_one",
        lambda sql, data: {"IsValid": 0, "IsAdmin": 0},
    )

    sellers = seller_service.SellerService().get_user_sellers(7)

    assert not sellers


def test_get_user_sellers_returns_all_sellers_when_user_id_is_none(monkeypatch):
    """
    Test that get_user_sellers returns all sellers when no user id is provided.
    """
    FakeSellerModel.instances = []
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    calls = []
    monkeypatch.setattr(
        seller_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [{"SellerId": 3, "Name": "A"}],
    )

    sellers = seller_service.SellerService().get_user_sellers(None)

    assert len(sellers) == 1
    assert FakeSellerModel.instances[0].seller_id == 3
    assert calls[0][1] is None


def test_get_user_sellers_returns_empty_when_user_lookup_is_missing(monkeypatch):
    """
    Test that get_user_sellers returns an empty list when the user row is missing.
    """
    monkeypatch.setattr(seller_service, "db_query_one", lambda sql, data: None)

    sellers = seller_service.SellerService().get_user_sellers(7)

    assert not sellers


def test_get_user_sellers_returns_all_sellers_for_admins(monkeypatch):
    """
    Test that get_user_sellers returns all sellers for admin users.
    """
    FakeSellerModel.instances = []
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    calls = []

    def fake_db_query_one(sql, data):  # pylint: disable=unused-argument
        return {"IsValid": 1, "IsAdmin": 1}

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        return [{"SellerId": 3, "Name": "A"}, {"SellerId": 0, "Name": "Skip"}]

    monkeypatch.setattr(seller_service, "db_query_one", fake_db_query_one)
    monkeypatch.setattr(seller_service, "db_query_all", fake_db_query_all)

    sellers = seller_service.SellerService().get_user_sellers(9)

    assert len(sellers) == 1
    assert FakeSellerModel.instances[0].seller_id == 3
    assert "SELECT SellerId, Name FROM Sellers ORDER BY Name" in calls[0][0]
    assert calls[0][1] is None


def test_get_user_sellers_filters_for_non_admin_users(monkeypatch):
    """
    Test that get_user_sellers loads only assigned sellers for non-admin users.
    """
    FakeSellerModel.instances = []
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    calls = []

    monkeypatch.setattr(
        seller_service,
        "db_query_one",
        lambda sql, data: {"IsValid": 1, "IsAdmin": 0},
    )
    monkeypatch.setattr(
        seller_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [{"SellerId": 8, "Name": "Band"}],
    )

    sellers = seller_service.SellerService().get_user_sellers(11)

    assert len(sellers) == 1
    assert FakeSellerModel.instances[0].seller_id == 8
    assert "LEFT JOIN UserSeller" in calls[0][0]
    assert calls[0][1] == {"userId": 11}


def test_get_all_sellers_respects_show_inactive_flag(monkeypatch):
    """
    Test that get_all_sellers filters inactive sellers unless explicitly requested.
    """
    FakeSellerModel.instances = []
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    calls = []
    monkeypatch.setattr(
        seller_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [{"SellerId": 4, "Name": "Band"}],
    )

    sellers = seller_service.SellerService().get_all_sellers(show_inactive=False)

    assert len(sellers) == 1
    assert "WHERE Inactive <> 1" in calls[0][0]
    assert FakeSellerModel.instances[0].seller_id == 4


def test_get_all_sellers_includes_inactive_when_requested(monkeypatch):
    """
    Test that get_all_sellers omits the inactive filter when inactive sellers are requested.
    """
    FakeSellerModel.instances = []
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    calls = []
    monkeypatch.setattr(
        seller_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [{"SellerId": 4, "Name": "Band"}],
    )

    sellers = seller_service.SellerService().get_all_sellers(show_inactive=True)

    assert len(sellers) == 1
    assert "WHERE Inactive <> 1" not in calls[0][0]


def test_get_all_sellers_skips_invalid_seller_rows(monkeypatch):
    """
    Test that get_all_sellers skips seller rows without a valid seller id.
    """
    FakeSellerModel.instances = []
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    monkeypatch.setattr(
        seller_service,
        "db_query_all",
        lambda sql, data: [{"SellerId": 0, "Name": "Skip"}],
    )

    sellers = seller_service.SellerService().get_all_sellers()

    assert not sellers
    assert not FakeSellerModel.instances


def test_update_seller_inserts_new_seller_and_new_categories(monkeypatch):
    """
    Test that update_seller inserts a seller and new seller-event categories.
    """
    insert_calls = []
    seller_to_update = FakeSellerRecord(seller_id=0)
    seller_to_update.seller_event_categories = [
        FakeSellerEventCategory(
            seller_id=0,
            ticket_socket_id=10,
            event_category_id=100,
            seller_rate_percent=12.5,
        )
    ]
    FakeSellerModel.categories_by_seller_id = {5: []}
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        if "INSERT INTO Sellers" in sql:
            return 5
        return 77

    monkeypatch.setattr(seller_service, "db_insert", fake_db_insert)

    updated_seller = seller_service.SellerService().update_seller(seller_to_update)

    assert updated_seller is seller_to_update
    assert seller_to_update.seller_id == 5
    assert "INSERT INTO Sellers" in insert_calls[0][0]
    assert insert_calls[0][1]["country_id"] == 1
    assert insert_calls[1][1] == {
        "sellerId": 5,
        "ticketSocketId": 10,
        "eventCategoryId": 100,
        "isVisibleOnSite": 1,
        "isVisibleOnPortal": 1,
        "sellerRatePercent": 12.5,
    }
    assert seller_to_update.seller_event_categories[0].seller_event_category_id == 77


def test_update_seller_returns_seller_without_category_sync_when_no_categories(
    monkeypatch,
):
    """
    Test that update_seller returns the seller when there are no categories to synchronize.
    """
    update_calls = []
    seller_to_update = FakeSellerRecord(seller_id=9)
    seller_to_update.seller_event_categories = []
    monkeypatch.setattr(
        seller_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    updated_seller = seller_service.SellerService().update_seller(seller_to_update)

    assert updated_seller is seller_to_update
    assert len(update_calls) == 1


def test_update_seller_updates_existing_seller_and_syncs_categories(monkeypatch):
    """
    Test that update_seller updates seller rows,
    updates changed categories, and deletes removed ones.
    """
    update_calls = []
    delete_calls = []
    seller_to_update = FakeSellerRecord(seller_id=9)
    seller_to_update.seller_event_categories = [
        FakeSellerEventCategory(
            seller_id=9,
            ticket_socket_id=10,
            event_category_id=200,
            seller_event_category_id=101,
            is_visible_on_site=False,
            seller_rate_percent=15.0,
        ),
        FakeSellerEventCategory(
            seller_id=9,
            ticket_socket_id=11,
            event_category_id=0,
            seller_event_category_id=0,
        ),
    ]
    FakeSellerModel.categories_by_seller_id = {
        9: [
            FakeSellerEventCategory(
                seller_id=9,
                ticket_socket_id=10,
                event_category_id=100,
                seller_event_category_id=101,
                is_visible_on_site=True,
                seller_rate_percent=10.0,
            ),
            FakeSellerEventCategory(
                seller_id=9,
                ticket_socket_id=11,
                event_category_id=150,
                seller_event_category_id=202,
                is_visible_on_site=True,
                seller_rate_percent=20.0,
            ),
        ]
    }
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    monkeypatch.setattr(
        seller_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        seller_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    updated_seller = seller_service.SellerService().update_seller(seller_to_update)

    assert updated_seller is seller_to_update
    assert "UPDATE Sellers SET" in update_calls[0][0]
    assert update_calls[1][1] == {
        "eventCategoryId": 200,
        "sellerEventCategoryId": 101,
        "isVisibleOnSite": 0,
        "isVisibleOnPortal": 1,
        "sellerRatePercent": 15.0,
    }
    assert delete_calls[0][1] == {"sellerEventCategoryId": 202}


def test_update_seller_leaves_unchanged_existing_categories_without_extra_writes(
    monkeypatch,
):
    """
    Test that update_seller leaves matching existing categories unchanged.
    """
    update_calls = []
    delete_calls = []
    seller_to_update = FakeSellerRecord(seller_id=9)
    seller_to_update.seller_event_categories = [
        FakeSellerEventCategory(
            seller_id=9,
            ticket_socket_id=10,
            event_category_id=100,
            seller_event_category_id=101,
            is_visible_on_site=True,
            is_visible_on_portal=True,
            seller_rate_percent=10.0,
        )
    ]
    FakeSellerModel.categories_by_seller_id = {
        9: [
            FakeSellerEventCategory(
                seller_id=9,
                ticket_socket_id=10,
                event_category_id=100,
                seller_event_category_id=101,
                is_visible_on_site=True,
                is_visible_on_portal=True,
                seller_rate_percent=10.0,
            )
        ]
    }
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    monkeypatch.setattr(
        seller_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        seller_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    updated_seller = seller_service.SellerService().update_seller(seller_to_update)

    assert updated_seller is seller_to_update
    assert len(update_calls) == 1
    assert not delete_calls


def test_update_seller_skips_invalid_new_categories_without_inserting(monkeypatch):
    """
    Test that update_seller skips unmatched categories that do not have valid insert data.
    """
    update_calls = []
    insert_calls = []
    seller_to_update = FakeSellerRecord(seller_id=9)
    seller_to_update.seller_event_categories = [
        FakeSellerEventCategory(
            seller_id=9,
            ticket_socket_id=0,
            event_category_id=0,
            seller_event_category_id=0,
        )
    ]
    FakeSellerModel.categories_by_seller_id = {9: []}
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)
    monkeypatch.setattr(
        seller_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        seller_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 77,
    )

    updated_seller = seller_service.SellerService().update_seller(seller_to_update)

    assert updated_seller is seller_to_update
    assert len(update_calls) == 1
    assert not insert_calls


def test_update_seller_returns_none_when_category_insert_fails(monkeypatch):
    """
    Test that update_seller returns None when a category insert fails.
    """
    seller_to_update = FakeSellerRecord(seller_id=0)
    seller_to_update.seller_event_categories = [
        FakeSellerEventCategory(
            seller_id=0,
            ticket_socket_id=12,
            event_category_id=300,
            seller_rate_percent=5.0,
        )
    ]
    FakeSellerModel.categories_by_seller_id = {6: []}
    monkeypatch.setattr(seller_service, "Seller", FakeSellerModel)

    def fake_db_insert(sql, data):  # pylint: disable=unused-argument
        if "INSERT INTO Sellers" in sql:
            return 6
        return 0

    monkeypatch.setattr(seller_service, "db_insert", fake_db_insert)

    updated_seller = seller_service.SellerService().update_seller(seller_to_update)

    assert updated_seller is None
