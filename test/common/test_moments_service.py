"""
Unit tests for common.moments_service helpers.
"""

from types import SimpleNamespace

from common import moments_service
from common.models.admin import FanMomentKey


class FakeS3Client:
    """
    Test double for the S3 client.
    """

    def __init__(self, keys=None):
        self.keys = keys or []
        self.uploads = []
        self.deletes = []

    def list_objects_v2(
        self, Bucket, Prefix="", Delimiter=None
    ):  # pylint: disable=invalid-name
        """
        Return S3-style object and prefix listings from in-memory keys.
        """
        matching_keys = [key for key in self.keys if key.startswith(Prefix)]
        if Delimiter is None:
            return {"Contents": [{"Key": key} for key in matching_keys]}

        contents = []
        common_prefixes = set()
        for key in matching_keys:
            remainder = key[len(Prefix) :]
            if Delimiter in remainder:
                folder = remainder.split(Delimiter, 1)[0]
                common_prefixes.add(f"{Prefix}{folder}{Delimiter}")
            elif len(remainder) > 0:
                contents.append({"Key": key})

        return {
            "Contents": contents,
            "CommonPrefixes": [
                {"Prefix": prefix} for prefix in sorted(common_prefixes)
            ],
        }

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        """
        Record upload calls.
        """
        self.uploads.append((filename, bucket, key, ExtraArgs))
        self.keys.append(key)

    def delete_objects(self, Bucket, Delete):  # pylint: disable=invalid-name
        """
        Record delete calls and return the deleted keys.
        """
        self.deletes.append((Bucket, Delete))
        deleted_keys = {item["Key"] for item in Delete["Objects"]}
        self.keys = [key for key in self.keys if key not in deleted_keys]
        return {"Deleted": Delete["Objects"]}


class RaisingS3Client:
    """
    Test double for S3 failures.
    """

    def __init__(self, fail_upload=False, fail_delete=False, fail_list=False):
        self.fail_upload = fail_upload
        self.fail_delete = fail_delete
        self.fail_list = fail_list

    def list_objects_v2(self, **kwargs):
        """
        Raise or return an empty list response.
        """
        if self.fail_list:
            raise RuntimeError("list failed")
        return {}

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        """
        Raise upload failures when configured.
        """
        if self.fail_upload:
            raise RuntimeError("upload failed")

    def delete_objects(self, Bucket, Delete):  # pylint: disable=invalid-name
        """
        Raise delete failures when configured.
        """
        if self.fail_delete:
            raise RuntimeError("delete failed")
        return {"Deleted": Delete["Objects"]}


class PaginatedS3Client:
    """
    Test double for paginated S3 listings.
    """

    def __init__(self):
        self.calls = []

    def list_objects_v2(self, **kwargs):
        """
        Return two pages of objects or prefixes.
        """
        self.calls.append(kwargs)
        is_second_page = "ContinuationToken" in kwargs
        if kwargs.get("Delimiter") == "/":
            if is_second_page:
                return {"CommonPrefixes": [{"Prefix": "2026-05-02/"}]}
            return {
                "CommonPrefixes": [{"Prefix": "2026-05-01/"}],
                "IsTruncated": True,
                "NextContinuationToken": "page-2",
            }
        if is_second_page:
            return {"Contents": [{"Key": "2026-05-02/400/b.jpg"}]}
        return {
            "Contents": [
                {"Key": "2026-05-01/300/"},
                {"Key": "2026-05-01/300/a.jpg"},
            ],
            "IsTruncated": True,
            "NextContinuationToken": "page-2",
        }


class FakeSeller:
    """
    Test seller lookup with deterministic names.
    """

    SELLER_NAMES = {
        10: "Zephyr Shows",
        20: "Alpha Presents",
    }

    def __init__(self, seller_id, get_event_categories=True):
        self.seller_id = seller_id
        self.name = self.SELLER_NAMES.get(seller_id)
        self.get_event_categories = get_event_categories


class FakeMomentEventService:
    """
    Test event lookup with deterministic sellers, dates, and titles.
    """

    EVENTS = {
        100: (10, "2026-04-30", "Delta Event"),
        200: (10, "2026-05-01", "Zephyr Event"),
        300: (20, "2026-05-01", "Alpha Event"),
        400: (20, "2026-05-02", "Bravo Event"),
    }

    def get_events_and_orders(
        self,
        get_orders=False,
        seller_id=None,
        event_id=None,
        is_public=False,
        ignore_flags=False,
    ):
        """
        Return configured events for the requested seller or event id.
        """
        event_ids = [event_id]
        if seller_id is not None:
            event_ids = [
                event_id
                for event_id, event_details in self.EVENTS.items()
                if event_details[0] == seller_id
            ]

        events = []
        for event_id in event_ids:
            event_seller_id, event_date, title = self.EVENTS[event_id]
            events.append(
                SimpleNamespace(
                    external_event_id=event_id,
                    seller_id=event_seller_id,
                    event_date=event_date,
                    title=title,
                    get_orders=get_orders,
                    is_public=is_public,
                )
            )
        return events

    def get_location_from_event(self, evt):
        """
        Return a deterministic event location.
        """
        return f"{evt.title} Location"


def build_fake_s3(monkeypatch):
    """
    Patch boto3 with a fake client loaded with moment keys.
    """
    fake_s3 = FakeS3Client(
        [
            "2026-05-01/300/b.jpg",
            "2026-05-01/200/a.jpg",
            "2026-04-30/100/c.png",
            "2026-05-02/400/d.jpg",
            "not-a-moment.txt",
            "2026-05-03/not-int/e.jpg",
        ]
    )
    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    return fake_s3


def build_fan_moment_row(
    event_id,
    event_date,
    seller_id,
    seller_name=None,
    event_title=None,
    images=None,
    venue=None,
    city=None,
    state=None,
    country=None,
    country_id=235,
):
    """
    Create a FanMoments index row for service tests.
    """
    if images is None:
        images = ["fan.jpg"]
    return {
        "FanMomentId": event_id,
        "ExternalEventId": event_id,
        "EventDate": event_date,
        "SellerId": seller_id,
        "SellerName": seller_name,
        "EventTitle": event_title,
        "Images": images,
        "Venue": venue,
        "City": city,
        "State": state,
        "Country": country,
        "CountryId": country_id,
    }


def build_fake_fan_moment_db(monkeypatch, rows=None):
    """
    Patch FanMoments index reads with filter-aware in-memory rows.
    """
    default_images_by_event_id = {
        100: ["c.png"],
        200: ["a.jpg"],
        300: ["b.jpg"],
        400: ["d.jpg"],
    }
    if rows is None:
        rows = [
            build_fan_moment_row(
                event_id,
                details[1],
                details[0],
                FakeSeller.SELLER_NAMES.get(details[0]),
                details[2],
                default_images_by_event_id.get(event_id),
            )
            for event_id, details in FakeMomentEventService.EVENTS.items()
        ]

    def fake_db_query_all(sql, data=None):
        data = data or {}
        if "SELECT FanMomentId, ImageName" in sql:
            matching_image_rows = []
            fan_moment_ids = {
                value for key, value in data.items() if key.startswith("fan_moment_id")
            }
            for row in rows:
                if row["FanMomentId"] not in fan_moment_ids:
                    continue
                for image_name in row["Images"]:
                    matching_image_rows.append(
                        {
                            "FanMomentId": row["FanMomentId"],
                            "ImageName": image_name,
                        }
                    )
            return matching_image_rows

        if "FanMomentImages.ImageName AS ImageName" in sql:
            event_id = data.get("event_id")
            for row in rows:
                if row["ExternalEventId"] == event_id:
                    return [{"ImageName": image_name} for image_name in row["Images"]]
            return []

        matching_rows = []
        for row in rows:
            if len(row["Images"]) == 0:
                continue
            if "event_id" in data and row["ExternalEventId"] != data["event_id"]:
                continue
            if "seller_id" in data and row["SellerId"] != data["seller_id"]:
                continue
            if "start_date" in data and row["EventDate"] < data["start_date"]:
                continue
            if "end_date" in data and row["EventDate"] > data["end_date"]:
                continue
            matching_rows.append(row)

        matching_rows = sorted(
            matching_rows,
            key=lambda row: (row["EventDate"], row["ExternalEventId"]),
            reverse=True,
        )
        if "LIMIT 0," in sql:
            limit = int(sql.split("LIMIT 0,", 1)[1].strip())
            matching_rows = matching_rows[:limit]
        return matching_rows

    monkeypatch.setattr(moments_service, "db_query_all", fake_db_query_all)


def patch_fan_moment_index_writes(monkeypatch):
    """
    Patch FanMoments index writes away for tests focused on S3 behavior.
    """
    monkeypatch.setattr(moments_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(moments_service, "db_insert", lambda sql, data: 1)
    monkeypatch.setattr(moments_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(moments_service, "db_delete", lambda sql, data: True)
    monkeypatch.setattr(moments_service, "db_query_all", lambda sql, data=None: [])


def create_fan_moment_key(moment_date="2026-05-10", seller_id=33, event_id=44):
    """
    Create a FanMomentKey for upload and delete tests.
    """
    fm_key = FanMomentKey()
    fm_key.moment_date = moment_date
    fm_key.seller_id = seller_id
    fm_key.event_id = event_id
    return fm_key


def test_get_available_moment_dates_returns_sorted_date_folders(monkeypatch):
    """
    Test that date folders are read from the bucket root and sorted ascending.
    """
    build_fake_s3(monkeypatch)

    dates = moments_service.MomentsService().get_available_moment_dates()

    assert dates == ["2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03"]


def test_get_available_moment_dates_can_filter_by_seller(monkeypatch):
    """
    Test that date folders can be filtered by seller id.
    """
    build_fake_s3(monkeypatch)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)

    dates = moments_service.MomentsService().get_available_moment_dates(seller_id=20)

    assert dates == ["2026-05-01", "2026-05-02"]


def test_get_available_moment_sellers_returns_distinct_sellers_sorted_by_name(
    monkeypatch,
):
    """
    Test that sellers are collected distinctly across all dates and sorted by name.
    """
    build_fake_s3(monkeypatch)
    monkeypatch.setattr(moments_service, "Seller", FakeSeller)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)

    sellers = moments_service.MomentsService().get_available_moment_sellers()

    assert [(seller.seller_id, seller.name) for seller in sellers] == [
        (20, "Alpha Presents"),
        (10, "Zephyr Shows"),
    ]


def test_get_available_moment_sellers_can_filter_by_date_and_sort_by_name(
    monkeypatch,
):
    """
    Test that sellers can be read beneath a moment date folder and sorted by name.
    """
    build_fake_s3(monkeypatch)
    monkeypatch.setattr(moments_service, "Seller", FakeSeller)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)

    sellers = moments_service.MomentsService().get_available_moment_sellers(
        "2026-05-01"
    )

    assert [(seller.seller_id, seller.name) for seller in sellers] == [
        (20, "Alpha Presents"),
        (10, "Zephyr Shows"),
    ]


def test_get_available_moment_events_returns_distinct_events_sorted_by_id(
    monkeypatch,
):
    """
    Test that event options are collected distinctly from S3 keys and sorted by id.
    """
    build_fake_s3(monkeypatch)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)
    service = moments_service.MomentsService()

    assert [
        (event.event_id, event.location)
        for event in service.get_available_moment_events()
    ] == [
        (100, "Delta Event Location"),
        (200, "Zephyr Event Location"),
        (300, "Alpha Event Location"),
        (400, "Bravo Event Location"),
    ]
    assert [
        (event.event_id, event.location)
        for event in service.get_available_moment_events(seller_id=20)
    ] == [
        (300, "Alpha Event Location"),
        (400, "Bravo Event Location"),
    ]
    assert [
        (event.event_id, event.location)
        for event in service.get_available_moment_events("2026-05-01", 20)
    ] == [(300, "Alpha Event Location")]


def test_get_available_moment_events_keeps_ids_with_missing_event_details(monkeypatch):
    """
    Test unfiltered event discovery keeps S3 ids when details are missing.
    """
    fake_s3 = FakeS3Client(
        [
            "2026-05-01/999/a.jpg",
            "2026-05-01/300/b.jpg",
            "2026-05-02/999/c.jpg",
        ]
    )

    class MissingEventService:
        """
        Return no event details for S3 event ids.
        """

        def get_events_and_orders(
            self, event_id=None, get_orders=False, is_public=False
        ):
            return []

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    monkeypatch.setattr(moments_service, "EventService", MissingEventService)

    assert [
        (event.event_id, event.location)
        for event in moments_service.MomentsService().get_available_moment_events()
    ] == [(300, None), (999, None)]


def test_filter_moments_returns_matching_fan_moment_objects(monkeypatch):
    """
    Test that filter_moments returns FanMoment objects matching supplied filters.
    """
    build_fake_s3(monkeypatch)
    images_by_event_id = {
        100: ["c.png"],
        200: ["a.jpg"],
        300: ["b.jpg"],
        400: ["d.jpg"],
    }
    build_fake_fan_moment_db(
        monkeypatch,
        [
            build_fan_moment_row(
                event_id, details[1], details[0], images=images_by_event_id[event_id]
            )
            for event_id, details in FakeMomentEventService.EVENTS.items()
        ],
    )

    class EmptySeller:
        """
        Test seller with no loaded name.
        """

        def __init__(self, seller_id, get_event_categories=True):
            self.name = None

    class EmptyEventService:
        """
        Test event service with no loaded event details.
        """

        def get_events_and_orders(
            self,
            event_id=None,
            seller_id=None,
            get_orders=False,
            is_public=False,
            ignore_flags=False,
        ):
            event_sellers_by_id = {100: 10, 200: 10, 300: 20, 400: 20}
            event_ids = [event_id]
            if seller_id is not None:
                event_ids = [
                    event_id
                    for event_id, event_seller_id in event_sellers_by_id.items()
                    if event_seller_id == seller_id
                ]

            return [
                SimpleNamespace(
                    external_event_id=event_id,
                    seller_id=event_sellers_by_id[event_id],
                    title=None,
                )
                for event_id in event_ids
            ]

        def get_location_from_event(self, evt):
            return None

    monkeypatch.setattr(moments_service, "Seller", EmptySeller)
    monkeypatch.setattr(moments_service, "EventService", EmptyEventService)

    moments = moments_service.MomentsService().filter_moments(
        start_date="2026-05-01",
        seller_id=20,
    )

    assert [(m.moment_date, m.seller_id, m.event_id, m.images) for m in moments] == [
        ("2026-05-01", 20, 300, ["b.jpg"]),
        ("2026-05-02", 20, 400, ["d.jpg"]),
    ]
    assert moments[0].seller_name is None
    assert moments[0].event_title is None
    assert moments[0].event_location is None


def test_filter_moments_filters_by_inclusive_date_range(monkeypatch):
    """
    Test that filter_moments matches moments between optional start and end dates.
    """
    build_fake_s3(monkeypatch)
    build_fake_fan_moment_db(monkeypatch)
    monkeypatch.setattr(moments_service, "Seller", FakeSeller)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)

    moments = moments_service.MomentsService().filter_moments(
        start_date="2026-05-01",
        end_date="2026-05-02",
    )

    assert [(m.moment_date, m.seller_id, m.event_id, m.images) for m in moments] == [
        ("2026-05-01", 20, 300, ["b.jpg"]),
        ("2026-05-01", 10, 200, ["a.jpg"]),
        ("2026-05-02", 20, 400, ["d.jpg"]),
    ]


def test_filter_moments_without_filters_returns_eight_most_recent(monkeypatch):
    """
    Test unfiltered fan moments return only the eight newest event groups.
    """
    fake_s3 = FakeS3Client(
        [
            f"2026-05-{day:02d}/{100 + day}/fan.jpg"
            for day in range(1, 11)
        ]
    )
    build_fake_fan_moment_db(
        monkeypatch,
        [
            build_fan_moment_row(
                100 + day,
                f"2026-05-{day:02d}",
                20,
                "Seller 20",
                f"Event {100 + day}",
            )
            for day in range(1, 11)
        ],
    )

    class RecentSeller:
        """
        Test seller lookup for recent moment sorting.
        """

        def __init__(self, seller_id, get_event_categories=True):
            self.name = f"Seller {seller_id}"

    class RecentEventService:
        """
        Test event details for recent moment sorting.
        """

        def get_events_and_orders(
            self, event_id=None, get_orders=False, is_public=False
        ):
            return [
                SimpleNamespace(
                    external_event_id=event_id,
                    seller_id=20,
                    title=f"Event {event_id}",
                )
            ]

        def get_location_from_event(self, evt):
            return None

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    monkeypatch.setattr(moments_service, "Seller", RecentSeller)
    monkeypatch.setattr(moments_service, "EventService", RecentEventService)

    moments = moments_service.MomentsService().filter_moments()

    assert [(m.moment_date, m.event_id) for m in moments] == [
        ("2026-05-10", 110),
        ("2026-05-09", 109),
        ("2026-05-08", 108),
        ("2026-05-07", 107),
        ("2026-05-06", 106),
        ("2026-05-05", 105),
        ("2026-05-04", 104),
        ("2026-05-03", 103),
    ]


def test_filter_moments_event_id_overrides_seller_and_date_filters(monkeypatch):
    """
    Test that event_id matches across dates and ignores lower-precedence filters.
    """
    build_fake_s3(monkeypatch)
    build_fake_fan_moment_db(monkeypatch)
    monkeypatch.setattr(moments_service, "Seller", FakeSeller)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)

    moments = moments_service.MomentsService().filter_moments(
        start_date="2026-06-01",
        end_date="2026-06-01",
        seller_id=999,
        event_id=300,
    )

    assert [(m.moment_date, m.seller_id, m.event_id, m.images) for m in moments] == [
        ("2026-05-01", 20, 300, ["b.jpg"]),
    ]


def test_filter_moments_uses_database_images_for_seller_filters(monkeypatch):
    """
    Test seller filters ignore dates and use FanMomentImages rows.
    """
    build_fake_s3(monkeypatch)
    build_fake_fan_moment_db(monkeypatch)
    monkeypatch.setattr(moments_service, "Seller", FakeSeller)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)
    service = moments_service.MomentsService()
    listed_image_prefixes = []
    original_list_moment_images = (
        service._list_moment_images  # pylint: disable=protected-access
    )

    def list_moment_images(event_prefix):
        listed_image_prefixes.append(event_prefix)
        return original_list_moment_images(event_prefix)

    service._list_moment_images = list_moment_images  # pylint: disable=protected-access

    moments = service.filter_moments(start_date="2026-06-01", seller_id=20)

    assert listed_image_prefixes == []
    assert [
        (moment.moment_date, moment.seller_id, moment.event_id, moment.images)
        for moment in moments
    ] == [
        ("2026-05-01", 20, 300, ["b.jpg"]),
        ("2026-05-02", 20, 400, ["d.jpg"]),
    ]


def test_filter_moments_uses_database_index_before_listing_s3_images(monkeypatch):
    """
    Test that the FanMoments database index selects S3 event prefixes.
    """
    fake_s3 = FakeS3Client(
        [
            "2026-05-01/300/a.jpg",
            "2026-05-01/300/b.jpg",
            "2026-05-01/301/c.jpg",
            "2026-05-01/302/d.jpg",
        ]
    )
    db_calls = []

    def fake_db_query_all(sql, data=None):
        db_calls.append((sql, data))
        if "SELECT FanMomentId, ImageName" in sql:
            return [
                {"FanMomentId": 300, "ImageName": "a.jpg"},
                {"FanMomentId": 300, "ImageName": "b.jpg"},
                {"FanMomentId": 301, "ImageName": "c.jpg"},
            ]
        return [
            build_fan_moment_row(
                300,
                "2026-05-01",
                20,
                "Seller 20",
                "Event 300",
                ["a.jpg", "b.jpg"],
            ),
            build_fan_moment_row(
                301, "2026-05-01", 20, "Seller 20", "Event 301", ["c.jpg"]
            ),
        ]

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    monkeypatch.setattr(moments_service, "db_query_all", fake_db_query_all)

    moments = moments_service.MomentsService().filter_moments(
        start_date="2026-05-01",
        end_date="2026-05-01",
        seller_id=20,
    )

    assert len(db_calls) == 2
    assert db_calls[0][1] == {"seller_id": 20}
    assert db_calls[1][1] == {"fan_moment_id_0": 300, "fan_moment_id_1": 301}
    assert [
        (m.seller_name, m.event_title, m.event_location, m.images) for m in moments
    ] == [
        ("Seller 20", "Event 300", None, ["a.jpg", "b.jpg"]),
        ("Seller 20", "Event 301", None, ["c.jpg"]),
    ]


def test_filter_moments_sorts_by_date_seller_name_and_event_title(monkeypatch):
    """
    Test that filter_moments sorts by date, seller name, and event title.
    """
    fake_s3 = FakeS3Client(
        [
            "2026-05-02/303/later-alpha.jpg",
            "2026-05-01/302/early-zephyr.jpg",
            "2026-05-01/301/early-alpha-bravo.jpg",
            "2026-05-01/300/early-alpha-alpha.jpg",
        ]
    )
    build_fake_fan_moment_db(
        monkeypatch,
        [
            build_fan_moment_row(
                303,
                "2026-05-02",
                20,
                "Alpha Presents",
                "Alpha Event",
                ["later-alpha.jpg"],
            ),
            build_fan_moment_row(
                302,
                "2026-05-01",
                10,
                "Zephyr Shows",
                "Alpha Event",
                ["early-zephyr.jpg"],
            ),
            build_fan_moment_row(
                301,
                "2026-05-01",
                20,
                "Alpha Presents",
                "Bravo Event",
                ["early-alpha-bravo.jpg"],
            ),
            build_fan_moment_row(
                300,
                "2026-05-01",
                20,
                "Alpha Presents",
                "Alpha Event",
                ["early-alpha-alpha.jpg"],
            ),
        ],
    )

    class SortSeller:
        """
        Test seller lookup with names that differ from id order.
        """

        def __init__(self, seller_id, get_event_categories=True):
            self.name = {10: "Zephyr Shows", 20: "Alpha Presents"}[seller_id]

    class SortEventService:
        """
        Test event lookup with titles that differ from id order.
        """

        def get_events_and_orders(self, event_id, get_orders=False, is_public=False):
            seller_id = {300: 20, 301: 20, 302: 10}[event_id]
            title = {300: "Alpha Event", 301: "Bravo Event", 302: "Alpha Event"}[
                event_id
            ]
            return [SimpleNamespace(seller_id=seller_id, title=title)]

        def get_location_from_event(self, evt):
            return None

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    monkeypatch.setattr(moments_service, "Seller", SortSeller)
    monkeypatch.setattr(moments_service, "EventService", SortEventService)

    moments = moments_service.MomentsService().filter_moments("2026-05-01")

    assert [
        (m.moment_date, m.seller_name, m.event_title, m.images) for m in moments
    ] == [
        (
            "2026-05-01",
            "Alpha Presents",
            "Alpha Event",
            ["early-alpha-alpha.jpg"],
        ),
        (
            "2026-05-01",
            "Alpha Presents",
            "Bravo Event",
            ["early-alpha-bravo.jpg"],
        ),
        (
            "2026-05-01",
            "Zephyr Shows",
            "Alpha Event",
            ["early-zephyr.jpg"],
        ),
        (
            "2026-05-02",
            "Alpha Presents",
            "Alpha Event",
            ["later-alpha.jpg"],
        ),
    ]


def test_filter_moments_skips_invalid_prefixes_and_empty_image_folders(monkeypatch):
    """
    Test filter_moments skips FanMoments rows with no indexed images.
    """
    build_fake_fan_moment_db(
        monkeypatch,
        [
            build_fan_moment_row(
                300, "2026-05-01", 20, "Alpha Presents", "Alpha Event", []
            )
        ],
    )

    moments = moments_service.MomentsService().filter_moments("2026-05-01")

    assert moments == []


def test_get_moment_lists_image_names_from_database(monkeypatch):
    """
    Test that get_moment returns all indexed image names for the event.
    """
    monkeypatch.setattr(
        moments_service,
        "db_query_all",
        lambda sql, data=None: [
            {"ImageName": "fan.jpg"},
            {"ImageName": "nested/other.png"},
        ],
    )
    fm_key = create_fan_moment_key()

    moment = moments_service.MomentsService().get_moment(fm_key)

    assert moment.key is fm_key
    assert moment.images == ["fan.jpg", "nested/other.png"]


def test_get_moment_returns_none_without_required_key_fields():
    """
    Test that get_moment validates the supplied fan moment key.
    """
    service = moments_service.MomentsService()
    fm_key = create_fan_moment_key()
    fm_key.event_id = None

    assert service.get_moment(None) is None
    assert service.get_moment(fm_key) is None


def test_delete_moments_removes_all_objects_under_event_prefix(monkeypatch):
    """
    Test that delete_moments deletes every key beneath the event prefix.
    """
    patch_fan_moment_index_writes(monkeypatch)
    fake_s3 = FakeS3Client(
        [
            "2026-05-10/",
            "2026-05-10/44/",
            "2026-05-10/44/fan.jpg",
            "2026-05-10/44/nested/other.png",
            "2026-05-10/45/other-event.jpg",
            "2026-05-11/44/other-date.jpg",
        ]
    )
    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)

    success = moments_service.MomentsService().delete_moments(create_fan_moment_key())

    assert success is True
    assert fake_s3.deletes == [
        (
            "moments-bucket",
            {
                "Objects": [
                    {"Key": "2026-05-10/44/"},
                    {"Key": "2026-05-10/44/fan.jpg"},
                    {"Key": "2026-05-10/44/nested/other.png"},
                ],
                "Quiet": True,
            },
        )
    ]
    assert fake_s3.keys == [
        "2026-05-10/",
        "2026-05-10/45/other-event.jpg",
        "2026-05-11/44/other-date.jpg",
    ]


def test_delete_moments_removes_empty_date_folder_marker(monkeypatch):
    """
    Test that delete_moments removes the date marker when no date children remain.
    """
    patch_fan_moment_index_writes(monkeypatch)
    fake_s3 = FakeS3Client(
        [
            "2026-05-10/",
            "2026-05-10/44/",
            "2026-05-10/44/fan.jpg",
            "2026-05-11/44/other-date.jpg",
        ]
    )
    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)

    success = moments_service.MomentsService().delete_moments(create_fan_moment_key())

    assert success is True
    assert fake_s3.deletes == [
        (
            "moments-bucket",
            {
                "Objects": [
                    {"Key": "2026-05-10/44/"},
                    {"Key": "2026-05-10/44/fan.jpg"},
                ],
                "Quiet": True,
            },
        ),
        (
            "moments-bucket",
            {
                "Objects": [{"Key": "2026-05-10/"}],
                "Quiet": True,
            },
        ),
    ]
    assert fake_s3.keys == ["2026-05-11/44/other-date.jpg"]


def test_delete_moments_handles_none_missing_bucket_and_delete_errors(monkeypatch):
    """
    Test delete_moments validation, missing bucket, and delete-error branches.
    """
    service = moments_service.MomentsService()

    fm_key = create_fan_moment_key()

    assert service.delete_moments(None) is False
    fm_key.event_id = None
    assert service.delete_moments(fm_key) is False
    fm_key = create_fan_moment_key()

    monkeypatch.delenv("S3_BUCKET_MOMENTS", raising=False)
    assert service.delete_moments(fm_key) is False

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    service._list_keys = (  # pylint: disable=protected-access
        lambda prefix="", include_folder_markers=False: ["2026-05-10/44/fan.jpg"]
    )
    monkeypatch.setattr(
        moments_service.boto3,
        "client",
        lambda service_name: RaisingS3Client(fail_delete=True),
    )

    assert service.delete_moments(fm_key) is False


def test_fan_moment_index_sync_inserts_updates_and_deletes(monkeypatch):
    """
    Test FanMoments and FanMomentImages sync follows the current S3 folder.
    """
    fake_s3 = FakeS3Client(
        [
            "2026-05-10/44/a.jpg",
            "2026-05-10/44/b.jpg",
        ]
    )
    db_calls = []
    existing_row = {}
    existing_image_rows = []
    next_image_id = 20

    def fake_db_query_one(sql, data):
        db_calls.append(("query", data.copy()))
        return existing_row

    def fake_db_query_all(sql, data=None):
        db_calls.append(("query_all", data.copy()))
        return existing_image_rows

    def fake_db_insert(sql, data):
        db_calls.append(("insert", data.copy()))
        if "FanMomentImages" in sql:
            nonlocal next_image_id
            existing_image_rows.append(
                {
                    "FanMomentImageId": next_image_id,
                    "ImageName": data["image_name"],
                }
            )
            next_image_id += 1
            return next_image_id - 1
        return 9

    def fake_db_update(sql, data):
        db_calls.append(("update", data.copy()))
        return True

    def fake_db_delete(sql, data):
        db_calls.append(("delete", data.copy()))
        if "fan_moment_image_id" in data:
            existing_image_rows[:] = [
                row
                for row in existing_image_rows
                if row["FanMomentImageId"] != data["fan_moment_image_id"]
            ]
        elif "fan_moment_id" in data:
            existing_image_rows.clear()
        return True

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    monkeypatch.setattr(moments_service, "db_query_one", fake_db_query_one)
    monkeypatch.setattr(moments_service, "db_query_all", fake_db_query_all)
    monkeypatch.setattr(moments_service, "db_insert", fake_db_insert)
    monkeypatch.setattr(moments_service, "db_update", fake_db_update)
    monkeypatch.setattr(moments_service, "db_delete", fake_db_delete)

    service = moments_service.MomentsService()
    fm_key = create_fan_moment_key()

    assert (
        service._sync_fan_moment_index(fm_key) is True
    )  # pylint: disable=protected-access
    existing_row["FanMomentId"] = 9
    assert (
        service._sync_fan_moment_index(fm_key) is True
    )  # pylint: disable=protected-access
    fake_s3.keys = []
    assert (
        service._sync_fan_moment_index(fm_key) is True
    )  # pylint: disable=protected-access

    assert db_calls == [
        ("query", {"event_id": 44}),
        ("insert", {"event_id": 44}),
        ("query_all", {"fan_moment_id": 9}),
        ("insert", {"fan_moment_id": 9, "image_name": "a.jpg"}),
        ("insert", {"fan_moment_id": 9, "image_name": "b.jpg"}),
        ("query", {"event_id": 44}),
        ("update", {"event_id": 44}),
        ("query_all", {"fan_moment_id": 9}),
        ("query", {"event_id": 44}),
        ("delete", {"fan_moment_id": 9}),
        ("delete", {"event_id": 44}),
    ]


def test_moment_listing_helpers_handle_pagination_and_errors(monkeypatch):
    """
    Test S3 key and prefix listing pagination plus exception handling.
    """
    service = moments_service.MomentsService()
    paginated_s3 = PaginatedS3Client()
    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(
        moments_service.boto3, "client", lambda service_name: paginated_s3
    )

    assert service._list_keys("2026-05") == [  # pylint: disable=protected-access
        "2026-05-01/300/a.jpg",
        "2026-05-02/400/b.jpg",
    ]
    assert paginated_s3.calls[1]["ContinuationToken"] == "page-2"

    paginated_s3.calls = []
    assert service._list_common_prefixes() == [  # pylint: disable=protected-access
        "2026-05-01/",
        "2026-05-02/",
    ]
    assert paginated_s3.calls[1]["ContinuationToken"] == "page-2"

    monkeypatch.setattr(
        moments_service.boto3,
        "client",
        lambda service_name: RaisingS3Client(fail_list=True),
    )
    assert service._list_keys() == []  # pylint: disable=protected-access
    assert service._list_common_prefixes() == []  # pylint: disable=protected-access


def test_moment_helper_branches(monkeypatch, workspace_tmp_path):
    """
    Test small helper branches not naturally covered by route-level behavior.
    """
    service = moments_service.MomentsService()
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)

    assert (
        service._build_filter_prefix("2026-05-01", "2026-05-01") == "2026-05-01/"
    )  # pylint: disable=protected-access
    assert (  # pylint: disable=protected-access
        service._build_filter_prefix("2026-05-01", "2026-05-01", 300) == ""
    )
    assert service._build_filter_prefix("2026-05-01", "2026-05-02") == ""
    assert service._build_filter_prefix(event_id=300) == ""
    assert service._get_upload_path(None) is None  # pylint: disable=protected-access
    monkeypatch.delenv("API_FILE_PATH", raising=False)
    assert (
        service._get_upload_path("missing.jpg") is None
    )  # pylint: disable=protected-access
    assert service._get_upload_extra_args(
        "file.unknownext"
    ) == {  # pylint: disable=protected-access
        "ContentType": "application/octet-stream"
    }
    assert (
        service._parse_fan_moment_key("2026-05-01/300") is None
    )  # pylint: disable=protected-access
    assert (
        service._parse_fan_moment_key("2026-05-01/300/") is None
    )  # pylint: disable=protected-access
    assert (
        service._parse_fan_moment_key("bad-date/300/a.jpg") is None
    )  # pylint: disable=protected-access
    assert (
        service._is_moment_key_match("bad-key") is False
    )  # pylint: disable=protected-access
    assert service._is_moment_key_match(  # pylint: disable=protected-access
        "2026-05-01/300/a.jpg",
        start_date="2026-05-01",
        end_date="2026-05-02",
        seller_id=20,
        event_id=300,
    )
    assert (
        service._is_parsed_moment_match(  # pylint: disable=protected-access
            create_fan_moment_key("2026-05-01", 20, 300),
            start_date="2026-05-02",
        )
        is False
    )
    assert (
        service._is_parsed_moment_match(  # pylint: disable=protected-access
            create_fan_moment_key("2026-05-03", 20, 300),
            end_date="2026-05-02",
        )
        is False
    )
    assert (
        service._is_parsed_moment_match(  # pylint: disable=protected-access
            create_fan_moment_key("2026-05-01", 20, 300),
            seller_id=21,
        )
        is False
    )
    assert service._is_parsed_moment_match(  # pylint: disable=protected-access
        create_fan_moment_key("2026-05-01", 20, 300),
        start_date="2026-06-01",
        seller_id=20,
    )
    assert (
        service._is_parsed_moment_match(  # pylint: disable=protected-access
            create_fan_moment_key("2026-05-01", 20, 300),
            event_id=301,
        )
        is False
    )
    assert service._is_parsed_moment_match(  # pylint: disable=protected-access
        create_fan_moment_key("2026-05-01", 20, 300),
        start_date="2026-05-02",
        end_date="2026-05-02",
        seller_id=21,
        event_id=300,
    )
    assert (
        service._is_valid_date_folder(None) is False
    )  # pylint: disable=protected-access
    assert service._try_parse_int("abc") is None  # pylint: disable=protected-access

    direct_file = workspace_tmp_path / "direct.jpg"
    direct_file.write_text("photo", encoding="utf-8")
    assert service._get_upload_path(str(direct_file)) == str(
        direct_file
    )  # pylint: disable=protected-access

    tmp_dir = workspace_tmp_path / "tmp"
    tmp_dir.mkdir()
    temp_file = tmp_dir / "temp.jpg"
    temp_file.write_text("photo", encoding="utf-8")
    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))
    monkeypatch.setattr(moments_service.os, "name", "posix")
    assert service._get_upload_path("temp.jpg") == str(
        temp_file
    )  # pylint: disable=protected-access
    assert (
        service._get_upload_path("still-missing.jpg") is None
    )  # pylint: disable=protected-access


def test_available_seller_and_event_helpers_skip_invalid_keys(monkeypatch):
    """
    Test date-filtered seller/event helpers ignore non-integer event keys.
    """
    service = moments_service.MomentsService()
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)
    monkeypatch.setattr(
        service,
        "_list_keys",
        lambda prefix="": [
            "2026-05-01/not-int/a.jpg",
            "2026-05-01/300/a.jpg",
        ],
    )
    monkeypatch.setattr(
        service,
        "_get_sellers_from_ids",
        lambda seller_ids: sorted(seller_ids),
    )

    assert service.get_available_moment_sellers("2026-05-01") == [20]

    events = service.get_available_moment_events("2026-05-01", 20)
    assert [(event.event_id, event.location) for event in events] == [
        (300, "Alpha Event Location")
    ]


def test_get_events_from_ids_skips_missing_events_and_sorts_none_values(monkeypatch):
    """
    Test event hydration skips empty lookups and sorts events with None values.
    """

    class SparseEventService:
        """
        Fake event service with missing and partial event data.
        """

        def get_events_and_orders(
            self, get_orders=False, event_id=None, is_public=False
        ):
            if event_id == 1:
                return None
            if event_id == 2:
                return []
            if event_id == 3:
                return [
                    SimpleNamespace(external_event_id=3, event_date=None, title=None)
                ]
            return [
                SimpleNamespace(
                    external_event_id=event_id,
                    event_date="2026-05-01",
                    title="Alpha",
                )
            ]

    monkeypatch.setattr(moments_service, "EventService", SparseEventService)

    events = moments_service.MomentsService()._get_events_from_ids(
        {1, 2, 3, 4}
    )  # pylint: disable=protected-access

    assert [(evt.external_event_id, evt.event_date, evt.title) for evt in events] == [
        (4, "2026-05-01", "Alpha"),
        (3, None, None),
    ]
