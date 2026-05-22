"""
Unit tests for common.report_service helpers.
"""

from common import report_service


def test_get_missing_venue_events_maps_event_and_venue_data(monkeypatch):
    """
    Test that get_missing_venue_events maps database rows into event and venue objects.
    """
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [
            {
                "EventID": 7,
                "Title": "VIP Night",
                "EventDate": "2026-05-01",
                "Venue": "Arena",
                "Address": "123 Main",
                "City": "Austin",
                "State": "TX",
                "Zip": "73301",
                "Country": "USA",
            }
        ],
    )

    events = report_service.ReportService().get_missing_venue_events()

    assert len(events) == 1
    assert events[0].external_event_id == 7
    assert events[0].title == "VIP Night"
    assert events[0].event_date == "2026-05-01"
    assert events[0].venue.name == "Arena"
    assert events[0].venue.address1 == "123 Main"
    assert events[0].venue.city == "Austin"
    assert events[0].venue.state == "TX"
    assert events[0].venue.postal_code == "73301"
    assert events[0].venue.country == "USA"


def test_get_orphaned_and_missing_header_images_compares_bucket_and_database(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_header_images returns orphaned and missing files.
    """
    monkeypatch.setenv("S3_BUCKET_HEADERS", "header-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["c.jpg", "a.jpg", "orphan.jpg"],
    )
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"Image": "a.jpg"}, {"Image": "missing.jpg"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_header_images()

    assert report.orphaned == ["c.jpg", "orphan.jpg"]
    assert report.missing == ["missing.jpg"]


def test_get_orphaned_and_missing_header_images_ignores_null_database_images(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_header_images ignores null image rows and handles empty buckets.
    """
    monkeypatch.setenv("S3_BUCKET_HEADERS", "header-bucket")
    monkeypatch.setattr(report_service, "list_s3_images", lambda bucket_name: [])
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"Image": None}, {"Image": "missing.jpg"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_header_images()

    assert not report.orphaned
    assert report.missing == ["missing.jpg"]


def test_get_orphaned_and_missing_thumbnail_images_merges_page_and_event_images(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_thumbnail_images
    merges page and event thumbnails and skips http urls.
    """
    calls = []
    monkeypatch.setenv("S3_BUCKET_THUMBNAILS", "thumbnail-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["event.jpg", "orphan.jpg", "page.jpg"],
    )

    def fake_db_query_all(sql):
        calls.append(sql)
        if "FROM Pages" in sql:
            return [{"Thumbnail": "page.jpg"}]
        return [
            {"Thumbnail": "event.jpg"},
            {"Thumbnail": "missing.jpg"},
        ]

    monkeypatch.setattr(report_service, "db_query_all", fake_db_query_all)

    report = report_service.ReportService().get_orphaned_and_missing_thumbnail_images()

    assert len(calls) == 2
    assert report.orphaned == ["orphan.jpg"]
    assert report.missing == ["missing.jpg"]


def test_get_orphaned_and_missing_thumbnail_images_ignores_null_and_duplicate_values(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_thumbnail_images ignores null rows and duplicate event thumbnails.
    """
    monkeypatch.setenv("S3_BUCKET_THUMBNAILS", "thumbnail-bucket")
    monkeypatch.setattr(report_service, "list_s3_images", lambda bucket_name: [])

    def fake_db_query_all(sql):
        if "FROM Pages" in sql:
            return [{"Thumbnail": None}, {"Thumbnail": "shared.jpg"}]
        return [{"Thumbnail": "shared.jpg"}, {"Thumbnail": None}]

    monkeypatch.setattr(report_service, "db_query_all", fake_db_query_all)

    report = report_service.ReportService().get_orphaned_and_missing_thumbnail_images()

    assert not report.orphaned
    assert report.missing == ["shared.jpg"]


def test_get_orphaned_and_missing_thumbnail_images_reports_orphans_when_database_is_empty(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_thumbnail_images reports all bucket files as orphaned when the database list is empty.
    """
    monkeypatch.setenv("S3_BUCKET_THUMBNAILS", "thumbnail-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["event.jpg"],
    )

    def fake_db_query_all(sql):
        if "FROM Pages" in sql:
            return [{"Thumbnail": None}]
        return [{"Thumbnail": None}]

    monkeypatch.setattr(report_service, "db_query_all", fake_db_query_all)

    report = report_service.ReportService().get_orphaned_and_missing_thumbnail_images()

    assert report.orphaned == ["event.jpg"]
    assert not report.missing


def test_get_orphaned_and_missing_preview_images_handles_empty_bucket(monkeypatch):
    """
    Test that get_orphaned_and_missing_preview_images
    reports only missing files when the bucket is empty.
    """
    monkeypatch.setenv("S3_BUCKET_PREVIEW", "preview-bucket")
    monkeypatch.setattr(report_service, "list_s3_images", lambda bucket_name: [])
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"LinkPreviewImage": "preview.jpg"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_preview_images()

    assert not report.orphaned
    assert report.missing == ["preview.jpg"]


def test_get_orphaned_and_missing_preview_images_ignores_null_database_values(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_preview_images ignores null preview-image rows.
    """
    monkeypatch.setenv("S3_BUCKET_PREVIEW", "preview-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["preview.jpg", "orphan.jpg"],
    )
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"LinkPreviewImage": None}, {"LinkPreviewImage": "preview.jpg"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_preview_images()

    assert report.orphaned == ["orphan.jpg"]
    assert not report.missing


def test_get_orphaned_and_missing_logo_images_reports_orphans_and_missing(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_logo_images reports differences between bucket and database.
    """
    monkeypatch.setenv("S3_BUCKET_LOGOS", "logo-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["logo-a.png", "orphan-logo.png"],
    )
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"LogoOnly": "logo-a.png"}, {"LogoOnly": "missing-logo.png"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_logo_images()

    assert report.orphaned == ["orphan-logo.png"]
    assert report.missing == ["missing-logo.png"]


def test_get_orphaned_and_missing_logo_images_ignores_null_database_values(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_logo_images ignores null logo rows.
    """
    monkeypatch.setenv("S3_BUCKET_LOGOS", "logo-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["logo-a.png"],
    )
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"LogoOnly": None}, {"LogoOnly": "logo-a.png"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_logo_images()

    assert not report.orphaned
    assert not report.missing


def test_get_orphaned_and_missing_logo_images_handles_empty_buckets(monkeypatch):
    """
    Test that get_orphaned_and_missing_logo_images reports only missing files when the logo bucket is empty.
    """
    monkeypatch.setenv("S3_BUCKET_LOGOS", "logo-bucket")
    monkeypatch.setattr(report_service, "list_s3_images", lambda bucket_name: [])
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"LogoOnly": "logo-a.png"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_logo_images()

    assert not report.orphaned
    assert report.missing == ["logo-a.png"]


def test_get_orphaned_and_missing_banner_images_reads_home_banner_setting(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_banner_images
    compares the home banner setting to the bucket contents.
    """
    monkeypatch.setenv("S3_BUCKET_HOMEBANNERS", "banner-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["banner-a.jpg", "orphan-banner.jpg"],
    )
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"Value": "banner-a.jpg"}, {"Value": "missing-banner.jpg"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_banner_images()

    assert report.orphaned == ["orphan-banner.jpg"]
    assert report.missing == ["missing-banner.jpg"]


def test_get_orphaned_and_missing_banner_images_ignores_null_settings_rows(
    monkeypatch,
):
    """
    Test that get_orphaned_and_missing_banner_images ignores null banner-setting rows.
    """
    monkeypatch.setenv("S3_BUCKET_HOMEBANNERS", "banner-bucket")
    monkeypatch.setattr(
        report_service,
        "list_s3_images",
        lambda bucket_name: ["banner-a.jpg"],
    )
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"Value": None}, {"Value": "banner-a.jpg"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_banner_images()

    assert not report.orphaned
    assert not report.missing


def test_get_orphaned_and_missing_banner_images_handles_empty_buckets(monkeypatch):
    """
    Test that get_orphaned_and_missing_banner_images reports only missing files when the banner bucket is empty.
    """
    monkeypatch.setenv("S3_BUCKET_HOMEBANNERS", "banner-bucket")
    monkeypatch.setattr(report_service, "list_s3_images", lambda bucket_name: [])
    monkeypatch.setattr(
        report_service,
        "db_query_all",
        lambda sql: [{"Value": "banner-a.jpg"}],
    )

    report = report_service.ReportService().get_orphaned_and_missing_banner_images()

    assert not report.orphaned
    assert report.missing == ["banner-a.jpg"]
