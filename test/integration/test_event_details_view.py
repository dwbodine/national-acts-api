"""Compare the migrated view with the original event query on populated MariaDB."""

from pathlib import Path
import shutil

import pytest
from sqlalchemy import text
from tools import migrate
from test_migrations import database  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


def test_view_preserves_projection_and_downgrade_removes_it(database):
    run, engine, root = database
    project_root = Path(__file__).resolve().parents[2]
    shutil.copytree(
        project_root / "migrations/versions",
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    run("upgrade", migrate.MANUAL_TRANSFER)
    statements = [
        "INSERT INTO Sellers (SellerId, Name) VALUES (1, 'Example artist')",
        "INSERT INTO Country (CountryId, CountryCode, CountryName) VALUES (1, 'USA', 'United States')",
        "INSERT INTO ExternalEventVenues (VenueID, Venue, Address, City, State, Zip, CountryId, TimeZone) VALUES (1, 'Local venue', 'Local address', 'Local city', 'NY', '10001', 1, 'America/New_York')",
        "INSERT INTO ExchangeRates (ExchangeRateId, Name, Symbol, ServiceTokenId) VALUES (1, 'US Dollar', 'USD', 'test')",
        "INSERT INTO TicketSocket (TicketSocketId, AccountName, ServiceUrl, ExchangeRateId) VALUES (1, 'Example account', 'https://example.com', 1)",
        "INSERT INTO SellerEventCategory (SellerEventCategoryId, SellerId, TicketSocketId, EventCategoryId, IsVisibleOnSite, SellerRatePercent) VALUES (1, 1, 1, 1, 0, 12.5)",
        "INSERT INTO TicketSocketEvents (Id, EventId, SellerEventCategoryId, Title, EventDate, URL, Venue, Address, City, State, Zip, Country, IsSoldOut) VALUES (101, 1001, 1, 'Partner title', '2026-11-01', 'https://example.com/101', 'Partner venue', 'Partner address', 'Partner city', 'CA', '90001', 'Partner country', 1), (102, 1002, 1, 'Other partner title', '2026-11-02', 'https://example.com/102', 'Fallback venue', 'Fallback address', 'Fallback city', 'WA', '98001', 'Fallback country', 0)",
        "INSERT INTO ExternalEvents (EventId, TicketSocketEventId, SellerId, Title, EventDate, EventTime, ExternalEventVenueId, URL, Thumbnail, CheckInNotes) VALUES (11, 101, 1, 'Internal title', '2026-12-01', '19:00', 1, 'https://example.com/internal/11', 'internal.jpg', 'Front entrance'), (12, 102, 1, 'Fallback event', '2026-12-02', '20:00', NULL, NULL, NULL, NULL), (13, NULL, 1, 'Local only event', '2026-12-03', '21:00', NULL, NULL, NULL, NULL)",
        "INSERT INTO Tour (TourId, TourName, AnnounceDate) VALUES (1, 'Example tour', '2026-10-01 00:00:00')",
        "INSERT INTO TourEvent (TourId, ExternalEventId) VALUES (1, 11)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            "INSERT INTO EventNotes (EventNoteId, ExternalEventId, Note) VALUES (1, 11, 'Preserve event note'), (2, NULL, 'Unlinked note')"
        )
        connection.exec_driver_sql(
            "INSERT INTO FanMoments (FanMomentId, ExternalEventId) VALUES (1, 11)"
        )
        connection.exec_driver_sql(
            "INSERT INTO FanMomentImages (FanMomentImageId, FanMomentId, ImageName) VALUES (1, 1, 'example.jpg')"
        )
        original_schemas = {
            name: migrate.normalized_ddl(
                connection.exec_driver_sql(f"SHOW CREATE TABLE {name}").one()[1]
            )
            for name in ("EventNotes", "FanMoments", "TourEvent")
        }

    # Freeze the legacy joins independently of the evolving application query.
    original = """
        SELECT ExternalEvents.EventId AS ExternalEventId,
               TicketSocketEvents.Id AS TicketSocketEventId,
               TicketSocketEvents.EventId AS EventId,
               COALESCE(ExternalEvents.Title, TicketSocketEvents.Title) AS Title,
               COALESCE(ExternalEventVenues.Venue, TicketSocketEvents.Venue) AS Venue,
               COALESCE(ExternalEventVenues.Address, TicketSocketEvents.Address) AS Address,
               COALESCE(Country.CountryName, TicketSocketEvents.Country) AS Country,
               COALESCE(SellerEventCategory.IsVisibleOnSite, 1) AS IsVisibleOnSite,
               COALESCE(SellerEventCategory.SellerRatePercent, 0.0) AS SellerRatePercent,
               COALESCE(Tour.IsActive, 0) AS IsTourActive,
               COALESCE(TicketSocketEvents.IsSoldOut, 0) AS IsSoldOut
        FROM ExternalEvents
        JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId
        LEFT JOIN TicketSocketEvents ON TicketSocketEvents.Id = ExternalEvents.TicketSocketEventId
        LEFT JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
        LEFT JOIN ExternalEventVenues ON ExternalEventVenues.VenueID = ExternalEvents.ExternalEventVenueId
        LEFT JOIN Country ON Country.CountryId = ExternalEventVenues.CountryId
        LEFT JOIN TourEvent ON TourEvent.ExternalEventId = ExternalEvents.EventId
        LEFT JOIN Tour ON Tour.TourId = TourEvent.TourId
    """
    with engine.connect() as connection:
        expected = [
            dict(row)
            for row in connection.execute(
                text(original + " ORDER BY ExternalEvents.EventId")
            ).mappings()
        ]
    run("upgrade")
    with engine.begin() as connection:
        assert connection.exec_driver_sql(
            "SELECT EventId, Note FROM EventNotes WHERE EventNoteId=1"
        ).one() == (11, "Preserve event note")
        assert (
            connection.exec_driver_sql(
                "SELECT EventId FROM FanMoments WHERE FanMomentId=1"
            ).scalar_one()
            == 11
        )
        assert (
            connection.exec_driver_sql(
                "SELECT EventId FROM TourEvent WHERE TourId=1"
            ).scalar_one()
            == 11
        )
        connection.exec_driver_sql(
            "INSERT INTO TicketPartners (TicketPartnerId, Name) VALUES (3, 'Future partner')"
        )
        connection.exec_driver_sql(
            "INSERT INTO TicketPartnerEvents (TicketPartnerId, EventId, PartnerEventId) VALUES (3, 11, 999), (1, 12, NULL)"
        )
    with engine.connect() as connection:
        actual = [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM EventDetails ORDER BY EventId")
            ).mappings()
        ]
    # The current view uses internal EventId and includes TicketSocket mappings only.
    expected_view = [
        {
            (
                "EventId"
                if key == "ExternalEventId"
                else "TicketSocketNativeEventId" if key == "EventId" else key
            ): value
            for key, value in row.items()
        }
        for row in expected
        if row["TicketSocketEventId"] is not None
    ]
    assert [
        {key: row[key] for key in expected_view[0]} for row in actual
    ] == expected_view
    assert actual[0]["EventId"] == 11
    assert actual[0]["TicketSocketEventId"] == 101
    assert actual[0]["TicketSocketNativeEventId"] == 1001
    assert actual[0]["Venue"] == "Local venue"
    assert actual[0]["IsTourActive"] == 1
    assert actual[1]["Venue"] == "Fallback venue"
    assert len(actual) == 2
    run("downgrade", migrate.MANUAL_TRANSFER)
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SHOW FULL TABLES LIKE 'EventDetails'").first()
            is None
        )
        restored = [
            dict(row)
            for row in connection.execute(
                text(original + " ORDER BY ExternalEvents.EventId")
            ).mappings()
        ]
        assert restored == expected
        for name, ddl in original_schemas.items():
            assert (
                migrate.normalized_ddl(
                    connection.exec_driver_sql(f"SHOW CREATE TABLE {name}").one()[1]
                )
                == ddl
            )
        assert connection.exec_driver_sql(
            "SELECT ExternalEventId, Note FROM EventNotes WHERE EventNoteId=1"
        ).one() == (11, "Preserve event note")
        assert (
            connection.exec_driver_sql(
                "SELECT ExternalEventId FROM FanMoments WHERE FanMomentId=1"
            ).scalar_one()
            == 11
        )
        assert (
            connection.exec_driver_sql(
                "SELECT ImageName FROM FanMomentImages WHERE FanMomentImageId=1"
            ).scalar_one()
            == "example.jpg"
        )
