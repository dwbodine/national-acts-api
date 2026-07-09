"""
Route tests for admin and event API modules.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from api import admin_api, event_api


def build_service(**methods):
    """
    Create a simple service object for route tests.
    """
    return lambda: SimpleNamespace(**methods)


def test_admin_countries_returns_unauthorized_for_non_admin(
    monkeypatch, client, auth_headers
):
    """
    Return 401 when a non-admin user requests admin country data.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: False)

    response = client.get("/admin/countries", headers=auth_headers())

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_admin_refund_event_passes_flags_to_service(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward refund options to the admin service when refunding an event.
    """
    captured = {}

    class FakeAdminService:
        """
        Fake admin service for event refunds.
        """

        def refund_all_event_orders(
            self, event_id, refund_service_fees, mark_cancelled
        ):
            """
            Record the event refund arguments.
            """
            captured["args"] = (event_id, refund_service_fees, mark_cancelled)
            return True

    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(admin_api, "AdminService", FakeAdminService)

    response = client.post(
        "/admin/events/refund",
        headers=auth_headers(),
        json={"eventId": 44, "refundServiceFees": True, "markCancelled": False},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["args"] == (44, True, False)


def test_admin_add_note_requires_event_or_calendar_date(
    monkeypatch, client, auth_headers
):
    """
    Reject note creation when neither an event id nor calendar date is provided.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)

    response = client.post(
        "/admin/notes/add",
        headers=auth_headers(),
        json={"note": "Need details"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_admin_update_page_order_converts_payload_to_pages(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Convert posted page dictionaries into page objects before saving.
    """
    captured = {}

    class FakePageService:
        """
        Fake page service for page-order updates.
        """

        def update_seller_page_order(self, pages):
            """
            Record the posted pages.
            """
            captured["pages"] = pages
            return True

    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(admin_api, "PageService", FakePageService)

    response = client.post(
        "/admin/pages/order",
        headers=auth_headers(),
        json=[{"pageId": 7, "pageOrder": 3}],
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["pages"][0].page_id == 7
    assert captured["pages"][0].page_order == 3


def test_admin_featured_artist_routes_forward_service_requests(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Map featured artist payloads and return featured artist service data.
    """
    captured = {}

    class FakePageService:
        """
        Fake page service for featured artist admin routes.
        """

        def update_featured_artist_order(self, featured_artists):
            """
            Record featured artist order updates.
            """
            captured["order"] = featured_artists
            return True

        def get_page_sellers(self):
            """
            Return page sellers available for featured artists.
            """
            return [{"pageSellerId": 12, "displayName": "VIP Seller"}]

        def update_featured_artist(self, featured_artist):
            """
            Record a featured artist update.
            """
            captured["artist"] = featured_artist
            return {"featuredArtistId": featured_artist.featured_artist_id}

    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(admin_api, "PageService", FakePageService)

    order_response = client.post(
        "/admin/featured-artists/order",
        headers=auth_headers(),
        json=[
            {
                "featuredArtistId": 3,
                "featuredArtistOrder": 2,
                "pageSellerId": 12,
                "title": "Ada Beats",
            }
        ],
    )
    sellers_response = client.get(
        "/admin/featured-artists/page-sellers",
        headers=auth_headers(),
    )
    update_response = client.post(
        "/admin/featured-artists/update",
        headers=auth_headers(),
        json={
            "featuredArtistId": 3,
            "featuredArtistOrder": 4,
            "pageSellerId": 12,
            "title": "Ada Beats",
        },
    )

    assert order_response.status_code == 200
    assert parse_json_response(order_response) is True
    assert captured["order"][0].featured_artist_id == 3
    assert captured["order"][0].featured_artist_order == 2
    assert captured["order"][0].page_seller_id == 12
    assert captured["order"][0].title == "Ada Beats"
    assert sellers_response.status_code == 200
    assert parse_json_response(sellers_response) == [
        {"pageSellerId": 12, "displayName": "VIP Seller"}
    ]
    assert update_response.status_code == 200
    assert parse_json_response(update_response) == {"featuredArtistId": 3}
    assert captured["artist"].featured_artist_id == 3
    assert captured["artist"].featured_artist_order == 4


def test_admin_featured_artist_order_returns_false_when_no_artists_are_mapped(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return false when no featured artist order payloads can be converted.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "convert_json_to_snake_case_object",
        lambda item, model: None,
    )

    response = client.post(
        "/admin/featured-artists/order",
        headers=auth_headers(),
        json=[{"featuredArtistId": 3}],
    )

    assert response.status_code == 200
    assert parse_json_response(response) is False


def test_admin_update_tour_uses_add_for_new_tour(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Call add_tour when the submitted tour does not have an id yet.
    """
    captured = {}

    class FakeTourService:
        """
        Fake tour service for create and update routes.
        """

        def add_tour(self, tour):
            """
            Record a new tour submission.
            """
            captured["tour"] = tour
            return True

        def update_tour(self, tour):
            """
            Record an existing tour update.
            """
            captured["updated"] = tour
            return False

    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(admin_api, "TourService", FakeTourService)

    response = client.post(
        "/admin/tours/update",
        headers=auth_headers(),
        json={"tourId": 0, "tourName": "Summer Tour", "sellerId": 101},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["tour"].tour_id == 0
    assert captured["tour"].tour_name == "Summer Tour"


def test_admin_update_setting_aggregates_multiple_results(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return false when any site-setting update fails.
    """
    calls = []

    class FakeAdminService:
        """
        Fake admin service for site-setting updates.
        """

        def update_setting(self, setting):
            """
            Record each updated site setting.
            """
            calls.append(setting.setting_id)
            return setting.setting_id == 1

    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(admin_api, "AdminService", FakeAdminService)

    response = client.post(
        "/admin/settings/update",
        headers=auth_headers(),
        json=[
            {"settingId": 1, "settingName": "One"},
            {"settingId": 2, "settingName": "Two"},
        ],
    )

    assert response.status_code == 200
    assert parse_json_response(response) is False
    assert calls == [1, 2]


def test_admin_countries_returns_service_data(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return country data for authorized admin users.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "AdminService",
        build_service(get_all_countries=lambda: [{"countryId": 1}]),
    )

    response = client.get("/admin/countries", headers=auth_headers())

    assert response.status_code == 200
    assert parse_json_response(response) == [{"countryId": 1}]


def test_admin_cancel_event_validates_and_calls_service(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Reject empty event lists and pass valid cancel requests to the service.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "AdminService",
        build_service(
            cancel_event=lambda event_ids, cancelled: (
                captured.update({"args": (event_ids, cancelled)}) or True
            )
        ),
    )

    bad_response = client.post(
        "/admin/events/cancel",
        headers=auth_headers(),
        json={"eventIdList": []},
    )
    good_response = client.post(
        "/admin/events/cancel",
        headers=auth_headers(),
        json={"eventIdList": [7, 8], "cancelled": 1},
    )

    assert bad_response.status_code == 400
    assert bad_response.get_json() == {"msg": "Bad Request"}
    assert good_response.status_code == 200
    assert parse_json_response(good_response) is True
    assert captured["args"] == ([7, 8], True)


def test_admin_send_list_to_band_validates_event_id_and_calls_service(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Reject missing event ids and forward send-list flags to the service.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "AdminService",
        build_service(
            send_list_to_band=lambda event_id, is_sent: (
                captured.update({"args": (event_id, is_sent)}) or {"eventId": event_id}
            )
        ),
    )

    bad_response = client.post(
        "/admin/events/sendListToBand",
        headers=auth_headers(),
        json={"eventId": 0},
    )
    good_response = client.post(
        "/admin/events/sendListToBand",
        headers=auth_headers(),
        json={"eventId": 44, "isSent": 1},
    )

    assert bad_response.status_code == 400
    assert bad_response.get_json() == {"msg": "Bad Request"}
    assert good_response.status_code == 200
    assert parse_json_response(good_response) == {"eventId": 44}
    assert captured["args"] == (44, True)


def test_admin_ticket_socket_only_validates_seller_id_and_returns_events(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Reject invalid seller ids and return ticket-socket-only events for valid requests.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "AdminService",
        build_service(
            get_ticket_socket_events_only=lambda seller_id: [{"sellerId": seller_id}]
        ),
    )

    bad_response = client.get("/admin/events/ticketSocketOnly", headers=auth_headers())
    good_response = client.get(
        "/admin/events/ticketSocketOnly?sellerId=12",
        headers=auth_headers(),
    )

    assert bad_response.status_code == 400
    assert bad_response.get_json() == {"msg": "Bad Request"}
    assert good_response.status_code == 200
    assert parse_json_response(good_response) == [{"sellerId": 12}]


def test_admin_update_event_maps_request_payload(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Convert event JSON into a VipEvent object before saving.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "AdminService",
        build_service(
            update_event=lambda event: (captured.update({"event": event}) or True)
        ),
    )

    response = client.post(
        "/admin/events/update",
        headers=auth_headers(),
        json={"ticketSocketEventId": 44, "eventTitle": "VIP Night"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["event"].ticket_socket_event_id == 44
    assert captured["event"].event_title == "VIP Night"


def test_admin_faq_routes_forward_ids_and_payloads(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward faq ids and mapped faq objects across the faq admin routes.
    """
    captured = {"deleted": None, "down": None, "up": None, "faq": None}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "FaqService",
        build_service(
            delete_faq=lambda faq_id: captured.update({"deleted": faq_id}) or True,
            move_down=lambda faq_id: captured.update({"down": faq_id}) or True,
            move_up=lambda faq_id: captured.update({"up": faq_id}) or True,
            update_faq=lambda faq: captured.update({"faq": faq}) or True,
        ),
    )

    delete_response = client.post(
        "/admin/faq/delete",
        headers=auth_headers(),
        json={"faqId": "12"},
    )
    down_response = client.post(
        "/admin/faq/movedown",
        headers=auth_headers(),
        json={"faqId": "13"},
    )
    up_response = client.post(
        "/admin/faq/moveup",
        headers=auth_headers(),
        json={"faqId": "14"},
    )
    update_response = client.post(
        "/admin/faq/update",
        headers=auth_headers(),
        json={"faqId": 15, "question": "Q", "answer": "A", "faqCategoryId": 2},
    )

    assert delete_response.status_code == 200
    assert down_response.status_code == 200
    assert up_response.status_code == 200
    assert update_response.status_code == 200
    assert parse_json_response(update_response) is True
    assert captured["deleted"] == "12"
    assert captured["down"] == "13"
    assert captured["up"] == "14"
    assert captured["faq"].faq_id == 15
    assert captured["faq"].question == "Q"


def test_admin_calendar_note_routes_validate_and_forward_requests(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Validate calendar note inputs and forward successful note requests to the service.
    """
    captured = {"calendar": None, "deleted": None, "edited": None}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "CalendarService",
        build_service(
            get_calendar_notes=lambda start, end: (
                captured.update({"calendar": (start, end)}) or [{"noteId": 1}]
            ),
            delete_note=lambda note_id: captured.update({"deleted": note_id}) or True,
            edit_note=lambda note_id, note, note_date, note_title, is_completed: (
                captured.update(
                    {
                        "edited": (
                            note_id,
                            note,
                            note_date,
                            note_title,
                            is_completed,
                        )
                    }
                )
                or True
            ),
        ),
    )

    bad_calendar = client.get("/admin/notes/calendar", headers=auth_headers())
    good_calendar = client.get(
        "/admin/notes/calendar?start=100&end=200",
        headers=auth_headers(),
    )
    delete_response = client.post(
        "/admin/notes/delete",
        headers=auth_headers(),
        json={"noteId": 9},
    )
    bad_edit = client.post(
        "/admin/notes/edit",
        headers=auth_headers(),
        json={"noteId": 9},
    )
    good_edit = client.post(
        "/admin/notes/edit",
        headers=auth_headers(),
        json={
            "noteId": 9,
            "noteDate": "2026-04-24",
            "note": "Updated",
            "noteTitle": "Title",
            "isCompleted": 1,
        },
    )

    assert bad_calendar.status_code == 400
    assert good_calendar.status_code == 200
    assert parse_json_response(good_calendar) == [{"noteId": 1}]
    assert delete_response.status_code == 200
    assert parse_json_response(delete_response) is True
    assert bad_edit.status_code == 400
    assert good_edit.status_code == 200
    assert parse_json_response(good_edit) is True
    assert captured["calendar"] == (100, 200)
    assert captured["deleted"] == 9
    assert captured["edited"] == (9, "Updated", "2026-04-24", "Title", True)


def test_admin_order_routes_validate_and_forward_requests(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Validate order-route inputs and forward successful order requests to the service.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "OrderService",
        build_service(
            add_comped_order=lambda event_id, num_tickets: (
                captured.update({"comp": (event_id, num_tickets)}) or True
            ),
            refund_order=lambda order_id, refund_service_fees, mark_chargeback: (
                captured.update(
                    {
                        "refund": (
                            order_id,
                            refund_service_fees,
                            mark_chargeback,
                        )
                    }
                )
                or True
            ),
            get_orders=lambda **kwargs: captured.update({"search": kwargs})
            or [{"orderId": 5}],
            update_order=lambda order: captured.update({"order": order}) or True,
        ),
    )

    bad_comp = client.post(
        "/admin/orders/comp",
        headers=auth_headers(),
        json={"eventId": 0, "numTickets": 2},
    )
    good_comp = client.post(
        "/admin/orders/comp",
        headers=auth_headers(),
        json={"eventId": 44, "numTickets": 2},
    )
    refund_response = client.post(
        "/admin/orders/refund",
        headers=auth_headers(),
        json={"orderId": 12, "refundServiceFees": 1, "markChargeback": 0},
    )
    bad_search = client.get("/admin/orders/search?sTerm=ab", headers=auth_headers())
    good_search = client.get(
        "/admin/orders/search?sTerm=vip",
        headers=auth_headers(),
    )
    update_response = client.post(
        "/admin/orders/update",
        headers=auth_headers(),
        json={"ticketSocketOrderId": 88, "firstName": "Ada"},
    )

    assert bad_comp.status_code == 400
    assert good_comp.status_code == 200
    assert parse_json_response(good_comp) is True
    assert refund_response.status_code == 200
    assert parse_json_response(refund_response) is True
    assert bad_search.status_code == 400
    assert good_search.status_code == 200
    assert parse_json_response(good_search) == [{"orderId": 5}]
    assert update_response.status_code == 200
    assert parse_json_response(update_response) is True
    assert captured["comp"] == (44, 2)
    assert captured["refund"] == (12, True, False)
    assert captured["search"] == {"ignore_flags": True, "search_term": "vip"}
    assert captured["order"].ticket_socket_order_id == 88


def test_admin_permissions_and_page_routes_return_service_results(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return permission and page data and map page updates before saving.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "RoleService",
        build_service(get_all_permissions=lambda: [{"permissionId": 1}]),
    )
    monkeypatch.setattr(
        admin_api,
        "PageService",
        build_service(
            get_all_pages=lambda: [{"pageId": 3}],
            update_page=lambda page: captured.update({"page": page}) or True,
        ),
    )

    permissions_response = client.get("/admin/permissions", headers=auth_headers())
    pages_response = client.get("/admin/pages", headers=auth_headers())
    update_response = client.post(
        "/admin/pages/update",
        headers=auth_headers(),
        json={"pageId": 8, "route": "seller-a"},
    )

    assert permissions_response.status_code == 200
    assert parse_json_response(permissions_response) == [{"permissionId": 1}]
    assert pages_response.status_code == 200
    assert parse_json_response(pages_response) == [{"pageId": 3}]
    assert update_response.status_code == 200
    assert parse_json_response(update_response) is True
    assert captured["page"].page_id == 8
    assert captured["page"].route == "seller-a"


def test_admin_role_routes_validate_and_forward_requests(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Validate role-route inputs and forward successful role requests to the service.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "RoleService",
        build_service(
            get_all_roles=lambda: [{"roleId": 2}],
            get_role_by_id=lambda role_id: {"roleId": role_id},
            delete_roles=lambda role_ids: captured.update({"deleted": role_ids})
            or True,
            update_role=lambda role: captured.update({"role": role}) or True,
        ),
    )

    all_response = client.get("/admin/roles", headers=auth_headers())
    bad_role = client.get("/admin/roles/1", headers=auth_headers())
    good_role = client.get("/admin/roles/3", headers=auth_headers())
    bad_delete = client.post("/admin/roles/delete", headers=auth_headers(), json=[])
    good_delete = client.post(
        "/admin/roles/delete",
        headers=auth_headers(),
        json=[2, 3],
    )
    update_response = client.post(
        "/admin/roles/update",
        headers=auth_headers(),
        json={"roleId": 4, "roleName": "Manager"},
    )

    assert all_response.status_code == 200
    assert parse_json_response(all_response) == [{"roleId": 2}]
    assert bad_role.status_code == 400
    assert good_role.status_code == 200
    assert parse_json_response(good_role) == {"roleId": 3}
    assert bad_delete.status_code == 400
    assert good_delete.status_code == 200
    assert parse_json_response(good_delete) is True
    assert update_response.status_code == 200
    assert parse_json_response(update_response) is True
    assert captured["deleted"] == [2, 3]
    assert captured["role"].role_id == 4
    assert captured["role"].role_name == "Manager"


def test_admin_seller_ticket_and_account_routes_return_service_results(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return seller and ticket account data and map seller updates before saving.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "SellerService",
        build_service(
            get_all_sellers=lambda show_inactive=True: [{"sellerId": 10}],
            update_seller=lambda seller: captured.update({"seller": seller})
            or {"sellerId": seller.seller_id},
        ),
    )
    monkeypatch.setattr(
        admin_api,
        "OrderService",
        build_service(
            refund_ticket=lambda ticket_id, refund_service_fees: (
                captured.update({"ticket": (ticket_id, refund_service_fees)}) or True
            )
        ),
    )
    monkeypatch.setattr(
        admin_api,
        "AdminService",
        build_service(get_ticket_socket_accounts=lambda: [{"ticketSocketId": 7}]),
    )

    sellers_response = client.get("/admin/sellers", headers=auth_headers())
    seller_update = client.post(
        "/admin/seller/update",
        headers=auth_headers(),
        json={"sellerId": 15, "name": "Seller Fifteen"},
    )
    bad_ticket = client.post(
        "/admin/tickets/refund",
        headers=auth_headers(),
        json={"ticketId": 0},
    )
    good_ticket = client.post(
        "/admin/tickets/refund",
        headers=auth_headers(),
        json={"ticketId": 5, "refundServiceFees": 1},
    )
    accounts_response = client.get(
        "/admin/ticketSocketAccounts", headers=auth_headers()
    )

    assert sellers_response.status_code == 200
    assert parse_json_response(sellers_response) == [{"sellerId": 10}]
    assert seller_update.status_code == 200
    assert parse_json_response(seller_update) == {"sellerId": 15}
    assert bad_ticket.status_code == 400
    assert good_ticket.status_code == 200
    assert parse_json_response(good_ticket) is True
    assert accounts_response.status_code == 200
    assert parse_json_response(accounts_response) == [{"ticketSocketId": 7}]
    assert captured["seller"].seller_id == 15
    assert captured["ticket"] == (5, True)


def test_admin_user_routes_validate_and_forward_requests(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return users and map delete and update requests before passing them to the service.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "UserService",
        build_service(
            get_all_users=lambda: [{"userId": 7}],
            delete_user=lambda user_id: captured.update({"deleted": user_id}) or True,
            update_user=lambda user: captured.update({"user": user}) or True,
        ),
    )

    users_response = client.get("/admin/users", headers=auth_headers())
    bad_delete = client.post(
        "/admin/users/delete",
        headers=auth_headers(),
        json={"userId": 0},
    )
    good_delete = client.post(
        "/admin/users/delete",
        headers=auth_headers(),
        json={"userId": 9},
    )
    update_response = client.post(
        "/admin/users/update",
        headers=auth_headers(),
        json={"userId": 11, "username": "ada@example.com"},
    )

    assert users_response.status_code == 200
    assert parse_json_response(users_response) == [{"userId": 7}]
    assert bad_delete.status_code == 400
    assert good_delete.status_code == 200
    assert parse_json_response(good_delete) is True
    assert update_response.status_code == 200
    assert parse_json_response(update_response) is True
    assert captured["deleted"] == 9
    assert captured["user"].user_id == 11
    assert captured["user"].username == "ada@example.com"


def test_admin_venue_routes_validate_and_forward_requests(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return venue data and map venue update and delete requests before saving.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "AdminService",
        build_service(
            get_external_venues=lambda search_term: [{"search": search_term}],
            update_external_venue=lambda venue: captured.update({"venue": venue})
            or {"venueId": venue.venue_id},
            delete_external_venue=lambda venue_id: (
                captured.update({"deleted": venue_id}) or True
            ),
        ),
    )

    venues_response = client.get(
        "/admin/venues?search=vip",
        headers=auth_headers(),
    )
    update_response = client.post(
        "/admin/venues/edit",
        headers=auth_headers(),
        json={"venueId": 4, "name": "VIP Hall"},
    )
    bad_delete = client.post(
        "/admin/venues/delete",
        headers=auth_headers(),
        json={"venueId": 0},
    )
    good_delete = client.post(
        "/admin/venues/delete",
        headers=auth_headers(),
        json={"venueId": 4},
    )

    assert venues_response.status_code == 200
    assert parse_json_response(venues_response) == [{"search": "vip"}]
    assert update_response.status_code == 200
    assert parse_json_response(update_response) == {"venueId": 4}
    assert bad_delete.status_code == 400
    assert good_delete.status_code == 200
    assert parse_json_response(good_delete) is True
    assert captured["venue"].venue_id == 4
    assert captured["deleted"] == 4


def test_event_get_events_and_orders_parses_query_arguments(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward parsed event-query filters to the event service.
    """
    captured = {}

    class FakeEventService:
        """
        Fake event service for event search queries.
        """

        def get_events_and_orders(self, **kwargs):
            """
            Record parsed event query arguments.
            """
            captured["kwargs"] = kwargs
            return [{"eventId": 44}]

    monkeypatch.setattr(event_api, "EventService", FakeEventService)

    response = client.get(
        (
            "/events/getEventsAndOrders?sellerId=10&start=100&end=200&excludeStart=150"
            "&excludeEnd=175&search=vip&deleted=1&inactive=0&hidden=1"
            "&eventId=44&tourId=5&excludeExternal=1&ignoreFlags=1"
            "&omitOrders=1&sellerIds=1,2&portal=1"
        ),
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"eventId": 44}]
    assert captured["kwargs"]["get_orders"] is False
    assert captured["kwargs"]["seller_id"] == 10
    assert captured["kwargs"]["seller_ids"] == [1, 2]
    assert captured["kwargs"]["show_inactive"] is True
    assert captured["kwargs"]["show_deleted"] is False
    assert captured["kwargs"]["show_hidden"] is True
    assert captured["kwargs"]["exclude_external"] is True
    assert captured["kwargs"]["ignore_flags"] is True
    assert captured["kwargs"]["is_portal"] is True


def test_event_order_by_id_rejects_missing_order_id(client, auth_headers):
    """
    Return 400 when the order-by-id route does not receive a valid order id.
    """
    response = client.get("/events/getOrderById", headers=auth_headers(role="user"))

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_event_order_by_id_returns_matching_orders(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return orders for a valid ticket-socket order id.
    """
    monkeypatch.setattr(
        event_api,
        "OrderService",
        build_service(
            get_orders=lambda ts_order_id=None: [{"ticketSocketOrderId": ts_order_id}]
        ),
    )

    response = client.get(
        "/events/getOrderById?tsOrderId=55",
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"ticketSocketOrderId": 55}]


def test_event_get_orders_forwards_filter_arguments(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward order-list filters to the order service.
    """
    captured = {}
    monkeypatch.setattr(
        event_api,
        "OrderService",
        build_service(
            get_orders=lambda seller_id, start, end, show_inactive, show_deleted, ignore_flags: (
                captured.update(
                    {
                        "args": (
                            seller_id,
                            start,
                            end,
                            show_inactive,
                            show_deleted,
                            ignore_flags,
                        )
                    }
                )
                or [{"orderId": 10}]
            )
        ),
    )

    response = client.get(
        "/events/getOrders?sellerId=9&start=100&end=200&inactive=1&deleted=0&ignoreFlags=1",
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"orderId": 10}]
    assert captured["args"] == (9, 100, 200, True, False, True)


def test_event_refresh_history_requires_admin(monkeypatch, client, auth_headers):
    """
    Return 401 when a non-admin user requests refresh history.
    """
    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=7, is_admin=False),
    )

    response = client.get(
        "/events/getRefreshHistory", headers=auth_headers(role="user")
    )

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_event_refresh_history_returns_logs_for_admin(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return refresh history logs for admin users.
    """
    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=7, is_admin=True),
    )
    monkeypatch.setattr(
        event_api,
        "AdminService",
        build_service(get_ticket_socket_refresh_history=lambda: [{"logId": 1}]),
    )

    response = client.get("/events/getRefreshHistory", headers=auth_headers())

    assert response.status_code == 200
    assert parse_json_response(response) == [{"logId": 1}]


def test_event_refresh_events_updates_rollups_on_success(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Rebuild daily-order rollups after a successful refresh request.
    """
    refresh_calls = {}
    order_calls = {}
    daily_calls = {}
    refresh_result = SimpleNamespace(succeeded=True, message="ok")

    class FakeDataRefreshService:
        """
        Fake refresh service for event-sync requests.
        """

        def refresh_database_from_ticket_socket(self, seller_id, start, end, user_id):
            """
            Record the refresh request.
            """
            refresh_calls["args"] = (seller_id, start, end, user_id)
            return refresh_result

    class FakeOrderService:
        """
        Fake order service for rollup rebuilds.
        """

        def get_orders(self, seller_id, start, end):
            """
            Record the rollup order lookup.
            """
            order_calls["args"] = (seller_id, start, end)
            return ["order-1"]

    class FakeDailyOrderService:
        """
        Fake daily-order service for refresh rollups.
        """

        def update_daily_order_data(self, orders, start, end, results):
            """
            Record the daily-order rollup update.
            """
            daily_calls["args"] = (orders, start, end, results)
            return {"updated": True}

    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=9, is_admin=True),
    )
    monkeypatch.setattr(event_api, "DataRefreshService", FakeDataRefreshService)
    monkeypatch.setattr(event_api, "OrderService", FakeOrderService)
    monkeypatch.setattr(event_api, "DailyOrderService", FakeDailyOrderService)

    response = client.get(
        "/events/refreshEventsFromService/55?start=1704067200&end=1706745600",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"updated": True}
    assert refresh_calls["args"] == (55, 1704067200, 1706745600, 9)
    assert order_calls["args"][0] == 55
    assert daily_calls["args"][0] == ["order-1"]
    assert daily_calls["args"][3] is refresh_result


def test_event_refresh_events_returns_none_for_invalid_seller(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return null when refresh is requested with an invalid seller id.
    """
    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=9, is_admin=True),
    )

    response = client.get(
        "/events/refreshEventsFromService/0",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert parse_json_response(response) is None


def test_event_set_events_deleted_requires_event_ids(client, auth_headers):
    """
    Return 400 when the delete-events route receives an empty id list.
    """
    response = client.post(
        "/events/setEventsDeleted",
        headers=auth_headers(role="user"),
        json={"eventIdList": []},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_event_set_events_deleted_returns_internal_error_on_failure(
    monkeypatch, client, auth_headers
):
    """
    Return 500 when deleting events fails in the service layer.
    """
    monkeypatch.setattr(
        event_api,
        "EventService",
        build_service(delete_events=lambda event_ids, deleted: False),
    )

    response = client.post(
        "/events/setEventsDeleted",
        headers=auth_headers(role="user"),
        json={"eventIdList": [1], "isDeleted": 1},
    )

    assert response.status_code == 500
    assert response.get_json() == {"msg": "Internal Server Error"}


def test_event_set_events_hidden_and_inactive_forward_flags(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward hidden and active flags to the event service routes.
    """
    captured = {}
    monkeypatch.setattr(
        event_api,
        "EventService",
        build_service(
            hide_events=lambda event_ids, hidden: (
                captured.update({"hidden": (event_ids, hidden)}) or True
            ),
            disable_events=lambda event_ids, disabled: (
                captured.update({"inactive": (event_ids, disabled)}) or True
            ),
        ),
    )

    hidden_response = client.post(
        "/events/setEventsHidden",
        headers=auth_headers(role="user"),
        json={"eventIdList": [2], "isHidden": 1},
    )
    inactive_response = client.post(
        "/events/setEventsInactive",
        headers=auth_headers(role="user"),
        json={"eventIdList": [3], "isActive": 0},
    )

    assert hidden_response.status_code == 200
    assert parse_json_response(hidden_response) is True
    assert inactive_response.status_code == 200
    assert parse_json_response(inactive_response) is True
    assert captured["hidden"] == ([2], True)
    assert captured["inactive"] == ([3], True)


def test_event_set_events_live_in_bands_in_town_returns_internal_error_on_failure(
    monkeypatch, client, auth_headers
):
    """
    Return 500 when marking events live in Bandsintown fails.
    """
    monkeypatch.setattr(
        event_api,
        "EventService",
        build_service(mark_events_live_in_bands_in_town=lambda event_ids: False),
    )

    response = client.post(
        "/events/setEventsLiveInBandsInTown",
        headers=auth_headers(role="user"),
        json={"eventIdList": [4]},
    )

    assert response.status_code == 500
    assert response.get_json() == {"msg": "Internal Server Error"}


def test_event_set_orders_deleted_and_tickets_checked_in_forward_flags(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward delete and check-in flags to the order service routes.
    """
    captured = {}
    monkeypatch.setattr(
        event_api,
        "OrderService",
        build_service(
            delete_orders=lambda order_ids, deleted: (
                captured.update({"deleted": (order_ids, deleted)}) or True
            ),
            check_in_tickets=lambda ticket_ids, checked_in: (
                captured.update({"checked_in": (ticket_ids, checked_in)}) or True
            ),
        ),
    )

    delete_response = client.post(
        "/events/setOrdersDeleted",
        headers=auth_headers(role="user"),
        json={"orderIdList": [7], "isDeleted": 1},
    )
    checkin_response = client.post(
        "/events/setTicketsCheckin",
        headers=auth_headers(role="user"),
        json={"ticketIdList": [8], "isCheckedIn": 0},
    )

    assert delete_response.status_code == 200
    assert parse_json_response(delete_response) is True
    assert checkin_response.status_code == 200
    assert parse_json_response(checkin_response) is True
    assert captured["deleted"] == ([7], True)
    assert captured["checked_in"] == ([8], False)


def test_event_tours_returns_all_tours_for_valid_seller(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return tours for a valid seller id.
    """
    monkeypatch.setattr(
        event_api,
        "TourService",
        build_service(get_all_tours=lambda seller_id: [{"sellerId": seller_id}]),
    )

    response = client.get("/events/tours/12", headers=auth_headers(role="user"))

    assert response.status_code == 200
    assert parse_json_response(response) == [{"sellerId": 12}]


def test_event_set_orders_inactive_inverts_is_active_flag(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Send the inverse active state to the order service when disabling orders.
    """
    captured = {}

    class FakeOrderService:
        """
        Fake order service for inactive-order updates.
        """

        def disable_orders(self, order_ids, disabled):
            """
            Record the order disable request.
            """
            captured["args"] = (order_ids, disabled)
            return True

    monkeypatch.setattr(event_api, "OrderService", FakeOrderService)

    response = client.post(
        "/events/setOrdersInactive",
        headers=auth_headers(role="user"),
        json={"orderIdList": [1, 2], "isActive": True},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["args"] == ([1, 2], False)


def test_event_tours_rejects_non_positive_seller_id(client, auth_headers):
    """
    Return 400 when the tours route receives a non-positive seller id.
    """
    response = client.get("/events/tours/0", headers=auth_headers(role="user"))

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


@pytest.mark.parametrize(
    ("route", "method", "json_body"),
    [
        ("/admin/events/cancel", "post", {"eventIdList": [1]}),
        ("/admin/events/refund", "post", {"eventId": 1}),
        ("/admin/events/sendListToBand", "post", {"eventId": 1}),
        ("/admin/events/ticketSocketOnly?sellerId=1", "get", None),
        ("/admin/events/update", "post", {"ticketSocketEventId": 1}),
        (
            "/admin/featured-artists/order",
            "post",
            [{"featuredArtistId": 1}],
        ),
        ("/admin/featured-artists/page-sellers", "get", None),
        (
            "/admin/featured-artists/update",
            "post",
            {"featuredArtistId": 1},
        ),
        ("/admin/faq/delete", "post", {"faqId": "1"}),
        ("/admin/faq/movedown", "post", {"faqId": "1"}),
        ("/admin/faq/moveup", "post", {"faqId": "1"}),
        ("/admin/faq/update", "post", {"faqId": 1}),
        (
            "/admin/moments/update",
            "post",
            {
                "key": {
                    "momentDate": "2026-05-01",
                    "sellerId": 20,
                    "eventId": 300,
                },
                "images": ["a.jpg"],
            },
        ),
        (
            "/admin/moments/delete",
            "post",
            {
                "momentDate": "2026-05-01",
                "sellerId": 20,
                "eventId": 300,
            },
        ),
        ("/admin/notes/add", "post", {"note": "Hello", "eventId": 1}),
        ("/admin/notes/calendar?start=1&end=2", "get", None),
        ("/admin/notes/delete", "post", {"noteId": 1}),
        ("/admin/notes/edit", "post", {"noteId": 1, "noteDate": "2026-04-24"}),
        ("/admin/orders/comp", "post", {"eventId": 1, "numTickets": 1}),
        ("/admin/orders/refund", "post", {"orderId": 1}),
        ("/admin/orders/search?sTerm=vip", "get", None),
        ("/admin/orders/update", "post", {"ticketSocketOrderId": 1}),
        ("/admin/permissions", "get", None),
        ("/admin/pages", "get", None),
        ("/admin/pages/order", "post", [{"pageId": 1}]),
        ("/admin/pages/update", "post", {"pageId": 1}),
        ("/admin/roles", "get", None),
        ("/admin/roles/2", "get", None),
        ("/admin/roles/delete", "post", [2]),
        ("/admin/roles/update", "post", {"roleId": 2}),
        ("/admin/sellers", "get", None),
        ("/admin/seller/update", "post", {"sellerId": 1}),
        ("/admin/settings/update", "post", [{"settingId": 1}]),
        ("/admin/tickets/refund", "post", {"ticketId": 1}),
        ("/admin/ticketSocketAccounts", "get", None),
        ("/admin/tours/update", "post", {"tourId": 1}),
        ("/admin/users", "get", None),
        ("/admin/users/delete", "post", {"userId": 1}),
        ("/admin/users/update", "post", {"userId": 1}),
        ("/admin/venues?search=vip", "get", None),
        ("/admin/venues/edit", "post", {"venueId": 1}),
        ("/admin/venues/delete", "post", {"venueId": 1}),
    ],
)
def test_admin_routes_require_admin_auth(
    monkeypatch, client, auth_headers, route, method, json_body
):
    """
    Return 401 when non-admin callers hit secured admin routes.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: False)
    request_kwargs = {"headers": auth_headers(role="user")}
    if json_body is not None:
        request_kwargs["json"] = json_body

    response = getattr(client, method)(route, **request_kwargs)

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("/admin/events/refund", {"eventId": 0}),
        ("/admin/notes/add", {"calendarDate": "2026-04-24"}),
        ("/admin/notes/delete", {"noteId": 0}),
        ("/admin/orders/refund", {"orderId": 0}),
        ("/admin/featured-artists/order", []),
        (
            "/admin/moments/delete",
            {
                "momentDate": "2026-05-01",
                "sellerId": 0,
                "eventId": 300,
            },
        ),
        ("/admin/pages/order", []),
        ("/admin/settings/update", []),
    ],
)
def test_admin_routes_validate_bad_request_payloads(
    monkeypatch, client, auth_headers, route, payload
):
    """
    Return 400 when admin routes receive invalid required payloads.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)

    response = client.post(route, headers=auth_headers(), json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_admin_add_note_returns_service_result_for_event_note(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward event note data to the calendar service when an event id is provided.
    """
    captured = {}
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "CalendarService",
        build_service(
            add_note=lambda note, event_id, calendar_date, note_title: (
                captured.update(
                    {
                        "args": (
                            note,
                            event_id,
                            calendar_date,
                            note_title,
                        )
                    }
                )
                or {"saved": True}
            )
        ),
    )

    response = client.post(
        "/admin/notes/add",
        headers=auth_headers(),
        json={"note": "VIP list sent", "eventId": 44},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"saved": True}
    assert captured["args"] == ("VIP list sent", 44, None, None)


def test_admin_update_page_order_returns_false_when_no_pages_are_mapped(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return false when none of the posted page entries can be converted.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "convert_json_to_snake_case_object",
        lambda item, model: None,
    )

    response = client.post(
        "/admin/pages/order",
        headers=auth_headers(),
        json=[{"pageId": 7}],
    )

    assert response.status_code == 200
    assert parse_json_response(response) is False


def test_admin_moments_add_and_delete_forward_valid_payloads(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Validate fan moment payloads and forward update/delete requests to the service.
    """
    captured = {}

    class FakeMomentsService:
        """
        Fake moments service for admin route tests.
        """

        def delete_moments(self, fm_key):
            """
            Record delete moment arguments.
            """
            captured["delete"] = fm_key
            return True

        def update_moment(self, fan_moment):
            """
            Record update moment arguments.
            """
            captured["update"] = fan_moment
            return True

    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(admin_api, "MomentsService", FakeMomentsService)

    payload = {
        "key": {
            "momentDate": "2026-05-01",
            "sellerId": 20,
            "eventId": 300,
        },
        "images": ["a.jpg", "b.jpg"],
    }
    update_response = client.post(
        "/admin/moments/update",
        headers=auth_headers(),
        json=payload,
    )
    delete_response = client.post(
        "/admin/moments/delete",
        headers=auth_headers(),
        json={
            "momentDate": "2026-05-01",
            "sellerId": "20",
            "eventId": "300",
        },
    )

    assert update_response.status_code == 200
    assert parse_json_response(update_response) is True
    assert delete_response.status_code == 200
    assert parse_json_response(delete_response) is True
    updated_moment = captured["update"]
    delete_key = captured["delete"]
    assert (
        updated_moment.key.moment_date,
        updated_moment.key.seller_id,
        updated_moment.key.event_id,
        updated_moment.images,
    ) == ("2026-05-01", 20, 300, ["a.jpg", "b.jpg"])
    assert (
        delete_key.moment_date,
        delete_key.seller_id,
        delete_key.event_id,
    ) == ("2026-05-01", 20, 300)


def test_admin_update_tour_rejects_missing_converted_tour(
    monkeypatch, client, auth_headers
):
    """
    Return 400 when the posted tour payload cannot be converted into a Tour object.
    """
    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        admin_api,
        "convert_json_to_snake_case_object",
        lambda item, model: None,
    )

    response = client.post(
        "/admin/tours/update",
        headers=auth_headers(),
        json={"tourId": 0},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_admin_update_tour_uses_update_for_existing_tour(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Call update_tour when the submitted tour already has an id.
    """
    captured = {}

    class FakeTourService:
        """
        Fake tour service for updating existing tours.
        """

        def add_tour(self, tour):
            """
            Fail if the add flow is used for an existing tour.
            """
            captured["added"] = tour
            return False

        def update_tour(self, tour):
            """
            Record the updated tour object.
            """
            captured["updated"] = tour
            return True

    monkeypatch.setattr(admin_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(admin_api, "TourService", FakeTourService)

    response = client.post(
        "/admin/tours/update",
        headers=auth_headers(),
        json={"tourId": 12, "tourName": "Arena Tour", "sellerId": 101},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["updated"].tour_id == 12
    assert "added" not in captured


def test_event_set_orders_deleted_returns_internal_error_on_failure(
    monkeypatch, client, auth_headers
):
    """
    Return 500 when deleting orders fails in the service layer.
    """
    monkeypatch.setattr(
        event_api,
        "OrderService",
        build_service(delete_orders=lambda order_ids, deleted: False),
    )

    response = client.post(
        "/events/setOrdersDeleted",
        headers=auth_headers(role="user"),
        json={"orderIdList": [7], "isDeleted": 1},
    )

    assert response.status_code == 500
    assert response.get_json() == {"msg": "Internal Server Error"}


def test_event_get_events_and_orders_uses_default_optional_filters(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Leave optional seller-id and portal filters unset when they are omitted.
    """
    captured = {}
    monkeypatch.setattr(
        event_api,
        "EventService",
        build_service(
            get_events_and_orders=lambda **kwargs: (
                captured.update({"kwargs": kwargs}) or [{"eventId": 55}]
            )
        ),
    )

    response = client.get(
        "/events/getEventsAndOrders?sellerId=10",
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"eventId": 55}]
    assert captured["kwargs"]["seller_ids"] is None
    assert captured["kwargs"]["is_portal"] is False


def test_event_refresh_events_requires_admin(monkeypatch, client, auth_headers):
    """
    Return 401 when a non-admin requests a manual TicketSocket refresh.
    """
    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=7, is_admin=False),
    )

    response = client.get(
        "/events/refreshEventsFromService/44",
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_event_refresh_events_returns_failed_refresh_without_rollups(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return the refresh result directly when the refresh does not succeed.
    """
    refresh_result = SimpleNamespace(succeeded=False, message="failed")
    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=9, is_admin=True),
    )
    monkeypatch.setattr(
        event_api,
        "DataRefreshService",
        build_service(
            refresh_database_from_ticket_socket=lambda seller_id, start, end, user_id: refresh_result
        ),
    )

    response = client.get(
        "/events/refreshEventsFromService/55?start=1704067200&end=1706745600",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {
        "succeeded": False,
        "message": "failed",
    }


def test_event_refresh_events_uses_current_year_when_start_is_missing(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Rebuild rollups for the current year when no historical start is provided.
    """
    order_calls = {}
    refresh_result = SimpleNamespace(succeeded=True, message="ok")

    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=9, is_admin=True),
    )
    monkeypatch.setattr(
        event_api,
        "DataRefreshService",
        build_service(
            refresh_database_from_ticket_socket=lambda seller_id, start, end, user_id: refresh_result
        ),
    )
    monkeypatch.setattr(
        event_api,
        "OrderService",
        build_service(
            get_orders=lambda seller_id, start, end: (
                order_calls.update({"args": (seller_id, start, end)}) or []
            )
        ),
    )
    monkeypatch.setattr(
        event_api,
        "DailyOrderService",
        build_service(
            update_daily_order_data=lambda orders, start, end, results: {
                "updated": True
            }
        ),
    )

    response = client.get(
        "/events/refreshEventsFromService/55",
        headers=auth_headers(),
    )

    pacific_tz = event_api.pytz.timezone("America/Los_Angeles")
    now = datetime.now(pacific_tz)
    expected_start = datetime.strptime(
        f"{now.year}-01-01 00:00:00",
        "%Y-%m-%d %H:%M:%S",
    ).timestamp()
    expected_end = datetime(now.year, now.month, now.day).timestamp()

    assert response.status_code == 200
    assert parse_json_response(response) == {"updated": True}
    assert order_calls["args"] == (55, expected_start, expected_end)


def test_event_refresh_events_clamps_future_year_to_current_year(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Rebuild rollups for the current year when the requested year is in the future.
    """
    order_calls = {}
    refresh_result = SimpleNamespace(succeeded=True, message="ok")
    future_start = int(datetime(2100, 1, 1).timestamp())

    monkeypatch.setattr(
        event_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=9, is_admin=True),
    )
    monkeypatch.setattr(
        event_api,
        "DataRefreshService",
        build_service(
            refresh_database_from_ticket_socket=lambda seller_id, start, end, user_id: refresh_result
        ),
    )
    monkeypatch.setattr(
        event_api,
        "OrderService",
        build_service(
            get_orders=lambda seller_id, start, end: (
                order_calls.update({"args": (seller_id, start, end)}) or []
            )
        ),
    )
    monkeypatch.setattr(
        event_api,
        "DailyOrderService",
        build_service(
            update_daily_order_data=lambda orders, start, end, results: {
                "updated": True
            }
        ),
    )

    response = client.get(
        f"/events/refreshEventsFromService/55?start={future_start}&end={future_start}",
        headers=auth_headers(),
    )

    pacific_tz = event_api.pytz.timezone("America/Los_Angeles")
    now = datetime.now(pacific_tz)
    expected_start = datetime.strptime(
        f"{now.year}-01-01 00:00:00",
        "%Y-%m-%d %H:%M:%S",
    ).timestamp()
    expected_end = datetime(now.year, now.month, now.day).timestamp()

    assert response.status_code == 200
    assert parse_json_response(response) == {"updated": True}
    assert order_calls["args"] == (55, expected_start, expected_end)


@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("/events/setEventsHidden", {"eventIdList": []}),
        ("/events/setEventsInactive", {"eventIdList": []}),
        ("/events/setEventsLiveInBandsInTown", {"eventIdList": []}),
        ("/events/setOrdersDeleted", {"orderIdList": []}),
        ("/events/setOrdersInactive", {"orderIdList": []}),
        ("/events/setTicketsCheckin", {"ticketIdList": []}),
    ],
)
def test_event_mutation_routes_reject_empty_id_lists(
    client, auth_headers, route, payload
):
    """
    Return 400 when event mutation routes receive empty id lists.
    """
    response = client.post(
        route,
        headers=auth_headers(role="user"),
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


@pytest.mark.parametrize(
    ("route", "service_name", "method_name", "payload"),
    [
        (
            "/events/setEventsHidden",
            "EventService",
            "hide_events",
            {"eventIdList": [2], "isHidden": 1},
        ),
        (
            "/events/setEventsInactive",
            "EventService",
            "disable_events",
            {"eventIdList": [3], "isActive": 0},
        ),
        (
            "/events/setOrdersInactive",
            "OrderService",
            "disable_orders",
            {"orderIdList": [4], "isActive": 1},
        ),
        (
            "/events/setTicketsCheckin",
            "OrderService",
            "check_in_tickets",
            {"ticketIdList": [5], "isCheckedIn": 1},
        ),
    ],
)
def test_event_mutation_routes_return_internal_error_on_service_failure(
    monkeypatch, client, auth_headers, route, service_name, method_name, payload
):
    """
    Return 500 when mutation service calls fail.
    """
    monkeypatch.setattr(
        event_api,
        service_name,
        build_service(**{method_name: lambda *args: False}),
    )

    response = client.post(
        route,
        headers=auth_headers(role="user"),
        json=payload,
    )

    assert response.status_code == 500
    assert response.get_json() == {"msg": "Internal Server Error"}


def test_event_set_events_deleted_returns_service_result(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return the delete-events service result for valid requests.
    """
    monkeypatch.setattr(
        event_api,
        "EventService",
        build_service(delete_events=lambda event_ids, deleted: True),
    )

    response = client.post(
        "/events/setEventsDeleted",
        headers=auth_headers(role="user"),
        json={"eventIdList": [1], "isDeleted": 1},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True


def test_event_set_events_live_in_bands_in_town_returns_service_result(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return the service result when marking events live in Bandsintown succeeds.
    """
    monkeypatch.setattr(
        event_api,
        "EventService",
        build_service(mark_events_live_in_bands_in_town=lambda event_ids: True),
    )

    response = client.post(
        "/events/setEventsLiveInBandsInTown",
        headers=auth_headers(role="user"),
        json={"eventIdList": [4]},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
