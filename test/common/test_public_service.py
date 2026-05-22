"""
Unit tests for common.public_service helpers.
"""

from pathlib import Path

from common import public_service


class FakeFile:
    """
    Test double for uploaded files.
    """

    def __init__(self, filename, save_callback):
        self.filename = filename
        self._save_callback = save_callback
        self.saved_paths = []

    def save(self, save_path):
        """
        Record the save path and delegate to the configured callback.
        """
        self.saved_paths.append(save_path)
        self._save_callback(save_path)


class FakeRequest:
    """
    Test double for Flask requests with uploaded files.
    """

    def __init__(self, file_obj):
        self.files = {"tempFile": file_obj}


def test_upload_image_to_bucket_saves_sanitized_file_and_uploads_png(
    monkeypatch, workspace_tmp_path
):
    """
    Test that upload_image_to_bucket sanitizes the filename, saves it, and uploads PNGs.
    """
    resize_calls = []
    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))
    tmp_dir = workspace_tmp_path / "tmp"
    tmp_dir.mkdir()

    def save_callback(save_path):
        Path(save_path).write_text("image-bytes", encoding="utf-8")

    request = FakeRequest(FakeFile("my image (1).png", save_callback))
    monkeypatch.setattr(
        public_service,
        "resize_and_move_temp_file_to_s3",
        lambda temp_filename, bucket_name, max_width, is_png: resize_calls.append(
            (temp_filename, bucket_name, max_width, is_png)
        )
        or "uploaded.png",
    )

    filename = public_service.PublicService().upload_image_to_bucket(
        request,
        "preview-bucket",
        400,
    )

    assert filename == "uploaded.png"
    assert request.files["tempFile"].saved_paths == [str(tmp_dir / "my_image_1_.png")]
    assert resize_calls == [("my_image_1_.png", "preview-bucket", 400, True)]


def test_upload_image_to_bucket_returns_none_when_temp_file_is_missing(
    monkeypatch, workspace_tmp_path
):
    """
    Test that upload_image_to_bucket returns None when the temp file is not written.
    """
    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))
    (workspace_tmp_path / "tmp").mkdir()
    request = FakeRequest(FakeFile("poster.jpg", lambda save_path: None))

    filename = public_service.PublicService().upload_image_to_bucket(
        request,
        "header-bucket",
        800,
    )

    assert filename is None


def test_upload_image_to_bucket_returns_none_when_upload_raises(
    monkeypatch, workspace_tmp_path
):
    """
    Test that upload_image_to_bucket returns None when saving or uploading raises an error.
    """
    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))
    (workspace_tmp_path / "tmp").mkdir()
    request = FakeRequest(
        FakeFile(
            "poster.jpg", lambda save_path: (_ for _ in ()).throw(RuntimeError("boom"))
        )
    )

    filename = public_service.PublicService().upload_image_to_bucket(
        request,
        "header-bucket",
        800,
    )

    assert filename is None


def test_get_featured_artists_maps_query_rows(monkeypatch):
    """
    Test that get_featured_artists maps joined database rows to FeaturedArtist models.
    """
    captured = {}

    def fake_db_query_all(sql):
        captured["sql"] = sql
        return [
            {
                "FeaturedArtistId": "3",
                "FeaturedArtistOrder": "1",
                "PageSellerId": "12",
                "Name": "Ada Beats",
                "BackgroundImage": "background.jpg",
                "LinkPreviewImage": "preview.jpg",
                "LogoOnly": "logo.png",
                "Route": "ada-beats",
            },
            {
                "FeaturedArtistId": 4,
                "FeaturedArtistOrder": 2,
                "PageSellerId": 13,
                "Name": "  The Nulls  ",
                "BackgroundImage": "",
                "LinkPreviewImage": None,
                "LogoOnly": "nulls-logo.png",
                "Route": "nulls",
            },
        ]

    monkeypatch.setattr(public_service, "db_query_all", fake_db_query_all)

    artists = public_service.PublicService().get_featured_artists()

    assert "FROM FeaturedArtists" in captured["sql"]
    assert "JOIN PageSellers" in captured["sql"]
    assert "ORDER BY FeaturedArtists.FeaturedArtistOrder" in captured["sql"]
    assert len(artists) == 2

    assert artists[0].featured_artist_id == 3
    assert artists[0].featured_artist_order == 1
    assert artists[0].page_seller_id == 12
    assert artists[0].title == "Ada Beats"
    assert artists[0].background_image == "background.jpg"
    assert artists[0].preview_image == "preview.jpg"
    assert artists[0].logo_image == "logo.png"
    assert artists[0].href == "ada-beats"

    assert artists[1].featured_artist_id == 4
    assert artists[1].title == "The Nulls"
    assert artists[1].background_image is None
    assert artists[1].preview_image is None
