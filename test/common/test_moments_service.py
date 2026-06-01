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

    def delete_objects(self, Bucket, Delete):  # pylint: disable=invalid-name
        """
        Record delete calls and return the deleted keys.
        """
        self.deletes.append((Bucket, Delete))
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

    def get_events_and_orders(self, get_orders=False, event_id=None, is_public=False):
        """
        Return the configured event for the requested event id.
        """
        seller_id, event_date, title = self.EVENTS[event_id]
        return [
            SimpleNamespace(
                external_event_id=event_id,
                seller_id=seller_id,
                event_date=event_date,
                title=title,
                get_orders=get_orders,
                is_public=is_public,
            )
        ]

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


def create_fan_moment_key(moment_date="2026-05-10", seller_id=33, event_id=44):
    """
    Create a FanMomentKey for upload and delete tests.
    """
    return FanMomentKey(moment_date, seller_id, event_id)


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


def test_get_available_moment_events_returns_distinct_events_sorted_by_date_and_title(
    monkeypatch,
):
    """
    Test that events are collected distinctly and sorted by date and title.
    """
    build_fake_s3(monkeypatch)
    monkeypatch.setattr(moments_service, "EventService", FakeMomentEventService)
    service = moments_service.MomentsService()

    assert [
        (evt.external_event_id, evt.event_date, evt.title)
        for evt in service.get_available_moment_events()
    ] == [
        (100, "2026-04-30", "Delta Event"),
        (300, "2026-05-01", "Alpha Event"),
        (200, "2026-05-01", "Zephyr Event"),
        (400, "2026-05-02", "Bravo Event"),
    ]
    assert [
        evt.external_event_id
        for evt in service.get_available_moment_events(seller_id=20)
    ] == [300, 400]
    assert [
        evt.external_event_id
        for evt in service.get_available_moment_events("2026-05-01", 20)
    ] == [300]


def test_filter_moments_returns_matching_fan_moment_objects(monkeypatch):
    """
    Test that filter_moments returns FanMoment objects matching supplied filters.
    """
    build_fake_s3(monkeypatch)

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

        def get_events_and_orders(self, event_id, get_orders=False, is_public=False):
            seller_id = {100: 10, 200: 10, 300: 20, 400: 20}[event_id]
            return [SimpleNamespace(seller_id=seller_id, title=None)]

        def get_location_from_event(self, evt):
            return None

    monkeypatch.setattr(moments_service, "Seller", EmptySeller)
    monkeypatch.setattr(moments_service, "EventService", EmptyEventService)

    moments = moments_service.MomentsService().filter_moments(seller_id=20)

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


def test_filter_moments_caches_seller_and_event_lookups(monkeypatch):
    """
    Test that repeated seller and event ids are looked up once per filter call.
    """
    fake_s3 = FakeS3Client(
        [
            "2026-05-01/300/a.jpg",
            "2026-05-01/300/b.jpg",
            "2026-05-01/301/c.jpg",
        ]
    )
    seller_calls = []
    event_calls = []

    class FakeSeller:
        """
        Test seller lookup.
        """

        def __init__(self, seller_id, get_event_categories=True):
            seller_calls.append((seller_id, get_event_categories))
            self.name = f"Seller {seller_id}"

    class FakeEventService:
        """
        Test event service lookup.
        """

        def get_events_and_orders(self, event_id, get_orders=False, is_public=False):
            event_calls.append((event_id, get_orders, is_public))
            return [SimpleNamespace(seller_id=20, title=f"Event {event_id}")]

        def get_location_from_event(self, evt):
            return f"{evt.title} Location"

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    monkeypatch.setattr(moments_service, "Seller", FakeSeller)
    monkeypatch.setattr(moments_service, "EventService", FakeEventService)

    moments = moments_service.MomentsService().filter_moments(
        start_date="2026-05-01",
        end_date="2026-05-01",
        seller_id=20,
    )

    assert seller_calls == [(20, False)]
    assert event_calls == [(300, False, True), (301, False, True)]
    assert [
        (m.seller_name, m.event_title, m.event_location, m.images) for m in moments
    ] == [
        ("Seller 20", "Event 300", "Event 300 Location", ["a.jpg", "b.jpg"]),
        ("Seller 20", "Event 301", "Event 301 Location", ["c.jpg"]),
    ]


def test_filter_moments_sorts_by_date_seller_name_and_event_title(monkeypatch):
    """
    Test that filter_moments sorts by date, seller name, and event title.
    """
    fake_s3 = FakeS3Client(
        [
            "2026-05-02/300/later-alpha.jpg",
            "2026-05-01/302/early-zephyr.jpg",
            "2026-05-01/301/early-alpha-bravo.jpg",
            "2026-05-01/300/early-alpha-alpha.jpg",
        ]
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

    moments = moments_service.MomentsService().filter_moments()

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


def test_filter_moments_handles_missing_parsed_ids(monkeypatch):
    """
    Test filter_moments branches for parsed moments without seller or event ids.
    """
    service = moments_service.MomentsService()
    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    service._list_keys = lambda prefix: [
        "synthetic-key"
    ]  # pylint: disable=protected-access
    service._parse_fan_moment_key = lambda key: FanMomentKey(  # pylint: disable=protected-access
        "2026-05-01", None, None, "synthetic-key"
    )

    moments = service.filter_moments()

    assert len(moments) == 1
    assert moments[0].seller_id is None
    assert moments[0].seller_name is None
    assert moments[0].event_id is None
    assert moments[0].event_title is None
    assert moments[0].images == ["synthetic-key"]


def test_add_moments_uploads_files_to_event_prefix(monkeypatch, workspace_tmp_path):
    """
    Test that add_moments uploads local temp files to the event prefix.
    """
    fake_s3 = build_fake_s3(monkeypatch)
    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))
    tmp_dir = workspace_tmp_path / "tmp"
    tmp_dir.mkdir()
    (tmp_dir / "fan.jpg").write_text("photo", encoding="utf-8")

    uploaded = moments_service.MomentsService().add_moments(
        create_fan_moment_key(), ["fan.jpg"]
    )

    assert uploaded == ["2026-05-10/44/fan.jpg"]
    assert fake_s3.uploads == [
        (
            str(tmp_dir / "fan.jpg"),
            "moments-bucket",
            "2026-05-10/44/fan.jpg",
            {"ContentType": "image/jpeg"},
        )
    ]


def test_add_moments_handles_none_missing_bucket_missing_file_and_upload_errors(
    monkeypatch, workspace_tmp_path
):
    """
    Test add_moments validation, missing-file, and upload-error branches.
    """
    service = moments_service.MomentsService()

    fm_key = create_fan_moment_key()

    assert service.add_moments(fm_key, None) == []

    monkeypatch.delenv("S3_BUCKET_MOMENTS", raising=False)
    assert service.add_moments(fm_key, ["fan.jpg"]) == []
    assert service._get_bucket_name() is None  # pylint: disable=protected-access
    assert service._list_keys() == []  # pylint: disable=protected-access
    assert service._list_common_prefixes() == []  # pylint: disable=protected-access

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    fake_s3 = FakeS3Client()
    monkeypatch.setattr(moments_service.boto3, "client", lambda service_name: fake_s3)
    assert service.add_moments(fm_key, ["missing.jpg"]) == []
    assert not fake_s3.uploads

    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))
    tmp_dir = workspace_tmp_path / "tmp"
    tmp_dir.mkdir()
    (tmp_dir / "fan.jpg").write_text("photo", encoding="utf-8")
    monkeypatch.setattr(
        moments_service.boto3,
        "client",
        lambda service_name: RaisingS3Client(fail_upload=True),
    )

    assert service.add_moments(fm_key, ["fan.jpg"]) == []


def test_delete_moments_removes_files_from_event_prefix(monkeypatch):
    """
    Test that delete_moments deletes keys beneath the event prefix.
    """
    fake_s3 = build_fake_s3(monkeypatch)

    deleted = moments_service.MomentsService().delete_moments(
        create_fan_moment_key(), ["fan.jpg", "nested/other.png"]
    )

    assert deleted == [
        "2026-05-10/44/fan.jpg",
        "2026-05-10/44/other.png",
    ]
    assert fake_s3.deletes == [
        (
            "moments-bucket",
            {
                "Objects": [
                    {"Key": "2026-05-10/44/fan.jpg"},
                    {"Key": "2026-05-10/44/other.png"},
                ],
                "Quiet": True,
            },
        )
    ]


def test_delete_moments_handles_none_missing_bucket_and_delete_errors(monkeypatch):
    """
    Test delete_moments validation, missing bucket, and delete-error branches.
    """
    service = moments_service.MomentsService()

    fm_key = create_fan_moment_key()

    assert service.delete_moments(fm_key, None) == []

    monkeypatch.delenv("S3_BUCKET_MOMENTS", raising=False)
    assert service.delete_moments(fm_key, ["fan.jpg"]) == []

    monkeypatch.setenv("S3_BUCKET_MOMENTS", "moments-bucket")
    monkeypatch.setattr(
        moments_service.boto3,
        "client",
        lambda service_name: RaisingS3Client(fail_delete=True),
    )

    assert service.delete_moments(fm_key, ["fan.jpg"]) == []


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
        service._build_filter_prefix("2026-05-01", "2026-05-01", 20, 300)
        == "2026-05-01/300/"
    )
    assert (
        service._build_filter_prefix("2026-05-01", "2026-05-02") == ""
    )
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
            FanMomentKey("2026-05-01", 20, 300),
            start_date="2026-05-02",
        )
        is False
    )
    assert (
        service._is_parsed_moment_match(  # pylint: disable=protected-access
            FanMomentKey("2026-05-03", 20, 300),
            end_date="2026-05-02",
        )
        is False
    )
    assert (
        service._is_parsed_moment_match(  # pylint: disable=protected-access
            FanMomentKey("2026-05-01", 20, 300),
            seller_id=21,
        )
        is False
    )
    assert (
        service._is_parsed_moment_match(  # pylint: disable=protected-access
            FanMomentKey("2026-05-01", 20, 300),
            event_id=301,
        )
        is False
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

    monkeypatch.setattr(
        service, "_get_events_from_ids", lambda event_ids: sorted(event_ids)
    )

    assert service.get_available_moment_events("2026-05-01", 20) == [300]


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
