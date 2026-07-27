"""
Unit tests for common.utility helpers.
"""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from PIL import Image

from common.constants import (
    EVENT_THUMBNAIL_IMAGE_WIDTH,
    FEATURED_ARTIST_IMAGE_WIDTH,
    HEADER_IMAGE_WIDTH,
    HOMEBANNER_IMAGE_WIDTH,
    LOGO_IMAGE_WIDTH,
    PREVIEW_IMAGE_WIDTH,
    THUMBNAIL_IMAGE_WIDTH,
    ImageType,
)
from common.models.ticket_socket import TicketSocketOrder
from common import utility


class FakeS3Client:
    """
    Test double for the subset of the boto3 S3 client used by utility helpers.
    """

    def __init__(self, list_response=None, should_raise=False):
        self.deleted = []
        self.uploaded = []
        self.list_bucket = None
        self.list_response = list_response or {}
        self.should_raise = should_raise

    def upload_file(self, origin_file, bucket_name, image_file, **kwargs):
        """
        Record upload requests and optionally raise an exception.
        """
        extra_args = kwargs.get("ExtraArgs")
        if self.should_raise:
            raise RuntimeError("upload failed")
        self.uploaded.append((origin_file, bucket_name, image_file, extra_args))

    def list_objects_v2(self, **kwargs):
        """
        Return the configured S3 listing response.
        """
        self.list_bucket = kwargs.get("Bucket")
        return self.list_response

    def delete_object(self, **kwargs):
        """
        Record delete requests and optionally raise an exception.
        """
        bucket = kwargs.get("Bucket")
        key = kwargs.get("Key")
        if self.should_raise:
            raise RuntimeError("delete failed")
        self.deleted.append((bucket, key))


class FakeHttpResponse:
    """
    Test double for http.client response objects.
    """

    def __init__(self, status, payload=b"{}", reason="OK"):
        self.status = status
        self.payload = payload
        self.reason = reason

    def read(self):
        """
        Return the configured response body.
        """
        return self.payload


class FakeHttpsConnection:
    """
    Test double for http.client.HTTPSConnection.
    """

    instances = []
    response = FakeHttpResponse(200)
    should_raise = False

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.closed = False
        self.requests = []
        FakeHttpsConnection.instances.append(self)

    def request(self, method, url, *args, **kwargs):
        """
        Record outgoing HTTP requests and optionally raise an exception.
        """
        if FakeHttpsConnection.should_raise:
            raise RuntimeError("network failed")
        self.requests.append((method, url, args, kwargs))

    def getresponse(self):
        """
        Return the configured HTTP response.
        """
        return FakeHttpsConnection.response

    def close(self):
        """
        Record that the connection was closed.
        """
        self.closed = True


class FakeMessagingService:
    """
    Test double for MessagingService error notifications.
    """

    instances = []

    def __init__(self):
        self.sent = []
        FakeMessagingService.instances.append(self)

    def send_email(self, to, subject, html, to_name):
        """
        Record email notification requests.
        """
        self.sent.append((to, subject, html, to_name))


class RaisingHttpsConnection:
    """
    Test double for HTTPSConnection constructor failures.
    """

    def __init__(self, host, port, timeout):
        raise RuntimeError("connection failed")


class Person:
    """
    Simple object for JSON encoding tests.
    """

    def __init__(self):
        self.first_name = "Ada"
        self.last_name = "Lovelace"
        self.nested_value = SimpleNamespace(child_name="Grace")


def test_replace_none_updates_nested_dicts_and_lists():
    """
    Test that replace_none converts string None values recursively.
    """
    data = {"name": "None", "children": [{"value": "None"}, "kept"]}

    utility.replace_none(data)

    assert data == {"name": None, "children": [{"value": None}, "kept"]}


def test_convert_to_json_serializes_object_keys_as_camel_case():
    """
    Test that convert_to_json changes object attribute names to camelCase.
    """
    result = json.loads(utility.convert_to_json(Person()))

    assert result["firstName"] == "Ada"
    assert result["lastName"] == "Lovelace"
    assert result["nestedValue"]["childName"] == "Grace"


def test_convert_to_snake_case_serializes_object_keys_as_snake_case():
    """
    Test that convert_to_snake_case changes object attribute names to snake_case.
    """
    obj = SimpleNamespace(
        firstName="Ada", nestedValue=SimpleNamespace(childName="Grace")
    )

    result = json.loads(utility.convert_to_snake_case(obj))

    assert result == {"first_name": "Ada", "nested_value": {"child_name": "Grace"}}


def test_convert_json_to_snake_case_object_populates_typed_object():
    """
    Test that convert_json_to_snake_case_object maps camelCase JSON onto an object.
    """
    request_json = {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "notes": "None",
        "nestedValue": {"childName": "Grace"},
    }
    typed_object = SimpleNamespace()

    result = utility.convert_json_to_snake_case_object(request_json, typed_object)

    assert result is typed_object
    assert typed_object.first_name == "Ada"
    assert typed_object.last_name == "Lovelace"
    assert typed_object.notes is None
    assert typed_object.nested_value.child_name == "Grace"


def test_resize_tmp_image_resizes_existing_image(monkeypatch, workspace_tmp_path):
    """
    Test that resize_tmp_image creates a resized copy and removes the original file.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "photo.jpg"
    Image.new("RGB", (800, 400), color="red").save(image_path)
    monkeypatch.setenv("API_FILE_PATH", str(api_path))

    resized_name = utility.resize_tmp_image("photo.jpg", 400)

    assert resized_name is not None
    assert resized_name.startswith("photo_")
    assert resized_name.endswith(".jpg")
    assert not image_path.exists()
    resized_path = temp_dir / resized_name
    assert resized_path.exists()
    with Image.open(resized_path) as resized_image:
        assert resized_image.width == 400


@pytest.mark.parametrize(
    ("extension", "image_format"),
    (("bmp", "BMP"), ("webp", "WEBP"), ("tiff", "TIFF")),
)
def test_resize_tmp_image_supports_other_pillow_formats(
    monkeypatch, workspace_tmp_path, extension, image_format
):
    """
    Test that resizing is not limited to JPEG and PNG files.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / f"photo.{extension}"
    Image.new("RGB", (600, 300), color="purple").save(image_path, format=image_format)
    monkeypatch.setenv("API_FILE_PATH", str(api_path))

    resized_name = utility.resize_tmp_image(image_path.name, 200)

    assert resized_name is not None
    with Image.open(temp_dir / resized_name) as resized_image:
        assert resized_image.format == image_format
        assert resized_image.size == (200, 100)


def test_resize_tmp_image_supports_heic(monkeypatch, workspace_tmp_path):
    """
    Test that the registered pillow-heif plugin decodes and encodes HEIC files.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "photo.heic"
    Image.new("RGB", (600, 300), color="purple").save(image_path, format="HEIF")
    monkeypatch.setenv("API_FILE_PATH", str(api_path))

    resized_name = utility.resize_tmp_image(image_path.name, 200)

    assert resized_name is not None
    with Image.open(temp_dir / resized_name) as resized_image:
        assert resized_image.format == "HEIF"
        assert resized_image.size == (200, 100)


def test_resize_tmp_image_preserves_display_orientation(
    monkeypatch, workspace_tmp_path
):
    """
    Test that EXIF orientation is applied once and removed from the output.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "portrait.jpg"
    image = Image.new("RGB", (120, 60), color="purple")
    exif = image.getexif()
    exif[274] = 6  # Display by rotating 90 degrees clockwise.
    image.save(image_path, format="JPEG", exif=exif)
    monkeypatch.setenv("API_FILE_PATH", str(api_path))

    resized_name = utility.resize_tmp_image(image_path.name, 200)

    assert resized_name is not None
    with Image.open(temp_dir / resized_name) as resized_image:
        assert resized_image.size == (60, 120)
        assert resized_image.getexif().get(274, 1) == 1


def test_resize_tmp_image_preserves_animated_gif_frames(
    monkeypatch, workspace_tmp_path
):
    """
    Test that every frame in a multi-frame image is resized and retained.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "animated.gif"
    frames = [
        Image.new("RGB", (300, 150), color="red"),
        Image.new("RGB", (300, 150), color="blue"),
    ]
    frames[0].save(
        image_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=125,
        loop=0,
    )
    monkeypatch.setenv("API_FILE_PATH", str(api_path))

    resized_name = utility.resize_tmp_image(image_path.name, 100)

    assert resized_name is not None
    with Image.open(temp_dir / resized_name) as resized_image:
        assert resized_image.format == "GIF"
        assert resized_image.n_frames == 2
        assert resized_image.size == (100, 50)
        # GIF stores frame durations in centiseconds.
        assert resized_image.info["duration"] == 120


def test_resize_tmp_image_uses_default_thumbnail_size(monkeypatch, workspace_tmp_path):
    """
    Test that resize_tmp_image falls back to THUMBNAIL_SIZE when width is not provided.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "small.jpg"
    Image.new("RGB", (200, 100), color="blue").save(image_path)
    monkeypatch.setenv("API_FILE_PATH", str(api_path))
    monkeypatch.setenv("THUMBNAIL_SIZE", "300")

    resized_name = utility.resize_tmp_image("small.jpg")

    assert resized_name is not None
    with Image.open(temp_dir / resized_name) as resized_image:
        assert resized_image.width == 200


def test_resize_tmp_image_returns_none_when_source_is_missing(
    monkeypatch, workspace_tmp_path
):
    """
    Test that resize_tmp_image returns None when the source file does not exist.
    """
    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))

    assert utility.resize_tmp_image("missing.jpg", 100) is None


def test_resize_tmp_image_returns_none_when_file_has_no_extension(
    monkeypatch, workspace_tmp_path
):
    """
    Test that resize_tmp_image rejects image filenames without extensions.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "photo"
    Image.new("RGB", (100, 100), color="green").save(image_path, format="PNG")
    monkeypatch.setenv("API_FILE_PATH", str(api_path))

    assert utility.resize_tmp_image("photo", 50) is None


def test_resize_tmp_image_returns_none_when_pillow_raises(
    monkeypatch, workspace_tmp_path
):
    """
    Test that resize_tmp_image handles image-processing errors.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "broken.jpg"
    image_path.write_text("not an image", encoding="utf-8")
    monkeypatch.setenv("API_FILE_PATH", str(api_path))

    assert utility.resize_tmp_image("broken.jpg", 50) is None


def test_resize_tmp_image_returns_none_when_saved_file_is_missing(monkeypatch):
    """
    Test that resize_tmp_image returns None when Pillow save does not create a file.
    """

    class FakeImage:
        """
        Test double for a Pillow image that does not write a resized file.
        """

        filename = "photo.jpg"
        format = "JPEG"
        width = 100
        height = 100

        def thumbnail(self, size, resample):
            """
            Accept resize requests without touching the filesystem.
            """

        def save(self, resize_file_path, image_format):
            """
            Simulate a save call that does not create an output file.
            """

        def close(self):
            """
            Accept close calls without touching the filesystem.
            """

    monkeypatch.setenv("API_FILE_PATH", "api")
    monkeypatch.setattr(utility.Image, "open", lambda image_path: FakeImage())
    monkeypatch.setattr(
        utility.os.path,
        "exists",
        lambda path: "_" not in utility.os.path.basename(str(path)),
    )

    assert utility.resize_tmp_image("photo.jpg", 50) is None


def test_resize_and_move_temp_file_to_s3_handles_non_windows_paths(monkeypatch):
    """
    Test that resize_and_move_temp_file_to_s3 works when os.name is not nt.
    """
    monkeypatch.setattr(utility.os, "name", "posix")
    monkeypatch.setenv("API_FILE_PATH", "/api")
    monkeypatch.setattr(
        utility, "resize_tmp_image", lambda temp_filename, max_width: None
    )

    assert utility.resize_and_move_temp_file_to_s3("photo.jpg", "bucket", 400) is None


def test_resize_and_move_temp_file_to_s3_uploads_resized_jpeg(
    monkeypatch, workspace_tmp_path
):
    """
    Test that resize_and_move_temp_file_to_s3 uploads a resized JPEG image.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / "photo.jpg"
    Image.new("RGB", (800, 400), color="red").save(image_path)
    fake_s3 = FakeS3Client()
    monkeypatch.setenv("API_FILE_PATH", str(api_path))
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)

    result = utility.resize_and_move_temp_file_to_s3("photo.jpg", "bucket", 400)

    assert result is not None
    assert fake_s3.uploaded[0][1] == "bucket"
    assert fake_s3.uploaded[0][3] == {"ContentType": "image/jpeg"}
    assert not (temp_dir / result).exists()


@pytest.mark.parametrize("extension", ("heic", "heif"))
def test_resize_and_move_temp_file_to_s3_converts_heif_to_jpeg_before_resizing(
    monkeypatch, workspace_tmp_path, extension
):
    """
    Test that HEIC and HEIF uploads are converted to JPEG before resizing.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / f"photo.{extension}"
    Image.new("RGB", (800, 400), color="red").save(image_path, format="HEIF")
    fake_s3 = FakeS3Client()
    resize_calls = []
    original_resize = utility.resize_tmp_image

    def track_resize(image_name, resize_width, output_format=None):
        resize_calls.append((image_name, resize_width, output_format))
        return original_resize(image_name, resize_width, output_format)

    monkeypatch.setenv("API_FILE_PATH", str(api_path))
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)
    monkeypatch.setattr(utility, "resize_tmp_image", track_resize)

    result = utility.resize_and_move_temp_file_to_s3(image_path.name, "bucket", 400)

    assert result is not None
    assert resize_calls == [(image_path.name, 400, "JPEG")]
    assert result.endswith(".jpg")
    assert fake_s3.uploaded[0][2].endswith(".jpg")
    assert fake_s3.uploaded[0][3] == {"ContentType": "image/jpeg"}
    assert not image_path.exists()


@pytest.mark.parametrize("filename", ("mobile-upload.jpg", "blob"))
def test_resize_and_move_temp_file_to_s3_detects_heif_from_file_contents(
    monkeypatch, workspace_tmp_path, filename
):
    """
    Test HEIF detection when a mobile client supplies a misleading filename.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / filename
    Image.new("RGB", (800, 400), color="red").save(image_path, format="HEIF")
    fake_s3 = FakeS3Client()
    monkeypatch.setenv("API_FILE_PATH", str(api_path))
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)

    result = utility.resize_and_move_temp_file_to_s3(filename, "bucket", 400)

    assert result is not None
    assert result.endswith(".jpg")
    assert fake_s3.uploaded[0][2].endswith(".jpg")
    assert fake_s3.uploaded[0][3] == {"ContentType": "image/jpeg"}
    assert not image_path.exists()


@pytest.mark.parametrize(
    ("extension", "image_format", "content_type"),
    (
        ("bmp", "BMP", "image/bmp"),
        ("gif", "GIF", "image/gif"),
        ("tiff", "TIFF", "image/tiff"),
        ("webp", "WEBP", "image/webp"),
    ),
)
def test_resize_and_move_temp_file_to_s3_detects_content_type(
    monkeypatch,
    workspace_tmp_path,
    extension,
    image_format,
    content_type,
):
    """
    Test that S3 receives the MIME type registered for the Pillow format.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    image_path = temp_dir / f"photo.{extension}"
    Image.new("RGB", (800, 400), color="red").save(image_path, format=image_format)
    fake_s3 = FakeS3Client()
    monkeypatch.setenv("API_FILE_PATH", str(api_path))
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)

    result = utility.resize_and_move_temp_file_to_s3(image_path.name, "bucket", 400)

    assert result is not None
    assert fake_s3.uploaded[0][3] == {"ContentType": content_type}


def test_resize_and_move_temp_file_to_s3_returns_none_when_resize_fails(
    monkeypatch, workspace_tmp_path
):
    """
    Test that resize_and_move_temp_file_to_s3 returns None when resizing fails.
    """
    monkeypatch.setenv("API_FILE_PATH", str(workspace_tmp_path))
    monkeypatch.setattr(
        utility, "resize_tmp_image", lambda temp_filename, max_width: None
    )

    assert utility.resize_and_move_temp_file_to_s3("missing.jpg", "bucket", 400) is None


def test_resize_and_move_temp_file_to_s3_skips_upload_without_bucket(
    monkeypatch, workspace_tmp_path
):
    """
    Test that resize_and_move_temp_file_to_s3 keeps the file when no bucket is provided.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    resized_path = temp_dir / "resized.jpg"
    resized_path.write_text("image", encoding="utf-8")
    monkeypatch.setenv("API_FILE_PATH", str(api_path))
    monkeypatch.setattr(
        utility, "resize_tmp_image", lambda temp_filename, max_width: "resized.jpg"
    )

    result = utility.resize_and_move_temp_file_to_s3("photo.jpg", None, 400)

    assert result == "resized.jpg"
    assert resized_path.exists()


def test_resize_and_move_temp_file_to_s3_returns_none_when_upload_fails(
    monkeypatch, workspace_tmp_path
):
    """
    Test that resize_and_move_temp_file_to_s3 returns the resized filename after upload errors.
    """
    api_path = workspace_tmp_path / "api"
    temp_dir = api_path / "tmp"
    temp_dir.mkdir(parents=True)
    resized_path = temp_dir / "resized.jpg"
    resized_path.write_text("image", encoding="utf-8")
    fake_s3 = FakeS3Client(should_raise=True)
    monkeypatch.setenv("API_FILE_PATH", str(api_path))
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)
    monkeypatch.setattr(
        utility, "resize_tmp_image", lambda temp_filename, max_width: "resized.jpg"
    )

    assert utility.resize_and_move_temp_file_to_s3("photo.jpg", "bucket", 400) == (
        "resized.jpg"
    )


def test_list_s3_images_returns_empty_list_when_bucket_has_no_contents(monkeypatch):
    """
    Test that list_s3_images returns an empty list when S3 returns no contents.
    """
    fake_s3 = FakeS3Client(list_response={})
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)

    assert utility.list_s3_images("bucket") == []


def test_list_s3_images_filters_to_supported_image_extensions(monkeypatch):
    """
    Test that list_s3_images returns only supported image file extensions.
    """
    fake_s3 = FakeS3Client(
        list_response={
            "Contents": [
                {"Key": "one.jpg"},
                {"Key": "two.JPEG"},
                {"Key": "three.png"},
                {"Key": "notes.txt"},
            ]
        }
    )
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)

    assert utility.list_s3_images("bucket") == ["one.jpg", "two.JPEG", "three.png"]


def test_remove_file_deletes_s3_object(monkeypatch):
    """
    Test that remove_file deletes an S3 object and returns True.
    """
    fake_s3 = FakeS3Client()
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)

    assert utility.remove_file("image.jpg", "bucket") is True
    assert fake_s3.deleted == [("bucket", "image.jpg")]


def test_remove_file_returns_false_when_delete_fails(monkeypatch):
    """
    Test that remove_file returns False when S3 deletion raises an error.
    """
    fake_s3 = FakeS3Client(should_raise=True)
    monkeypatch.setattr(utility.boto3, "client", lambda service: fake_s3)

    assert utility.remove_file("image.jpg", "bucket") is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5551234567", "(555) 123-4567"),
        ("15551234567", "(555) 123-4567"),
        ("5551234", "555-1234"),
        ("12345", "12345"),
    ],
)
def test_format_phone_formats_expected_usa_lengths(raw, expected):
    """
    Test that format_phone formats 10-digit, 11-digit, 7-digit, and short values.
    """
    assert utility.format_phone(raw) == expected


def test_fix_magic_quotes_replaces_unicode_quotes():
    """
    Test that fix_magic_quotes normalizes curly quotes to ASCII quotes.
    """
    assert (
        utility.fix_magic_quotes("\u201cHello\u201d \u2018Ada\u2019")
        == "\"Hello\" 'Ada'"
    )


def test_add_months_rolls_year_forward():
    """
    Test that add_months rolls the year forward when adding past December.
    """
    assert utility.add_months(datetime(2026, 10, 23), 5) == datetime(2027, 3, 23)


@pytest.mark.parametrize(
    ("email", "is_valid"),
    [
        ("ada@example.com", True),
        ("ada.lovelace+test@example.co", True),
        ("not-an-email", False),
    ],
)
def test_validate_email_address_matches_valid_email_shapes(email, is_valid):
    """
    Test that validate_email_address accepts valid emails and rejects invalid strings.
    """
    assert (utility.validate_email_address(email) is not None) is is_valid


def test_get_https_response_returns_data_and_sets_headers(monkeypatch):
    """
    Test that get_https_response returns data and sends auth headers.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = False
    FakeHttpsConnection.response = FakeHttpResponse(
        200, payload=json.dumps({"data": {"ok": True}}).encode("utf-8")
    )
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)

    result = utility.get_https_response(
        "api.example.com", "/events", bearer_token="token", api_key="key"
    )

    connection = FakeHttpsConnection.instances[0]
    request = connection.requests[0]
    assert result == {"ok": True}
    assert request[0] == "GET"
    assert request[1] == "/events"
    assert request[3]["headers"]["Authorization"] == "Bearer token"
    assert request[3]["headers"]["x-api-key"] == "key"
    assert connection.closed is True


def test_get_https_response_returns_none_when_response_has_no_data(monkeypatch):
    """
    Test that get_https_response returns None when JSON has no data property.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = False
    FakeHttpsConnection.response = FakeHttpResponse(
        200, payload=json.dumps({"ok": True}).encode("utf-8")
    )
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)

    assert utility.get_https_response("api.example.com", "/events") is None


def test_get_https_response_returns_none_for_non_success_status(monkeypatch):
    """
    Test that get_https_response returns None for non-200 responses.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = False
    FakeHttpsConnection.response = FakeHttpResponse(500, reason="Server Error")
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)

    assert utility.get_https_response("api.example.com", "/events") is None


def test_get_https_response_sends_error_email_when_request_raises(monkeypatch):
    """
    Test that get_https_response sends an error email when the HTTP request fails.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = True
    FakeMessagingService.instances = []
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)
    monkeypatch.setattr(utility, "MessagingService", FakeMessagingService)

    assert utility.get_https_response("api.example.com", "/events") is None
    assert FakeHttpsConnection.instances[0].closed is True
    assert FakeMessagingService.instances[0].sent[0][0] == "dwbodine@gmail.com"
    assert "Error in get_https_response" in FakeMessagingService.instances[0].sent[0][1]


def test_get_https_response_handles_connection_constructor_error(monkeypatch):
    """
    Test that get_https_response handles errors before a connection exists.
    """
    FakeMessagingService.instances = []
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", RaisingHttpsConnection)
    monkeypatch.setattr(utility, "MessagingService", FakeMessagingService)

    assert utility.get_https_response("api.example.com", "/events") is None
    assert FakeMessagingService.instances[0].sent[0][0] == "dwbodine@gmail.com"


def test_post_https_response_returns_data_and_sets_headers(monkeypatch):
    """
    Test that post_https_response returns data and sends auth headers.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = False
    FakeHttpsConnection.response = FakeHttpResponse(
        200, payload=json.dumps({"data": [1, 2]}).encode("utf-8")
    )
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)

    result = utility.post_https_response(
        "api.example.com", "/orders", "{}", api_key="key", bearer_token="token"
    )

    connection = FakeHttpsConnection.instances[0]
    request = connection.requests[0]
    assert result == [1, 2]
    assert request[0] == "POST"
    assert request[1] == "/orders"
    assert request[2][0] == "{}"
    assert request[2][1]["Authorization"] == "Bearer token"
    assert request[2][1]["x-api-key"] == "key"
    assert connection.closed is True


def test_post_https_response_returns_none_when_response_has_no_data(monkeypatch):
    """
    Test that post_https_response returns None when JSON has no data property.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = False
    FakeHttpsConnection.response = FakeHttpResponse(
        200, payload=json.dumps({"ok": True}).encode("utf-8")
    )
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)

    assert utility.post_https_response("api.example.com", "/orders", "{}") is None


def test_post_https_response_returns_none_for_non_success_status(monkeypatch):
    """
    Test that post_https_response returns None for non-200 responses.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = False
    FakeHttpsConnection.response = FakeHttpResponse(400, reason="Bad Request")
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)

    assert utility.post_https_response("api.example.com", "/orders", "{}") is None


def test_post_https_response_sends_error_email_when_request_raises(monkeypatch):
    """
    Test that post_https_response sends an error email when the HTTP request fails.
    """
    FakeHttpsConnection.instances = []
    FakeHttpsConnection.should_raise = True
    FakeMessagingService.instances = []
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", FakeHttpsConnection)
    monkeypatch.setattr(utility, "MessagingService", FakeMessagingService)

    assert utility.post_https_response("api.example.com", "/orders", "{}") is None
    assert FakeHttpsConnection.instances[0].closed is True
    assert FakeMessagingService.instances[0].sent[0][0] == "dwbodine@gmail.com"
    assert (
        "Error in post_https_response" in FakeMessagingService.instances[0].sent[0][1]
    )


def test_post_https_response_handles_connection_constructor_error(monkeypatch):
    """
    Test that post_https_response handles errors before a connection exists.
    """
    FakeMessagingService.instances = []
    monkeypatch.setattr(utility.http.client, "HTTPSConnection", RaisingHttpsConnection)
    monkeypatch.setattr(utility, "MessagingService", FakeMessagingService)

    assert utility.post_https_response("api.example.com", "/orders", "{}") is None
    assert FakeMessagingService.instances[0].sent[0][0] == "dwbodine@gmail.com"


@pytest.mark.parametrize(
    ("override", "default", "expected"),
    [
        (" value ", None, "value"),
        ("", " fallback ", "fallback"),
        (None, None, None),
    ],
)
def test_get_override_string_value_or_default_returns_expected_value(
    override, default, expected
):
    """
    Test that get_override_string_value_or_default prefers non-blank overrides.
    """
    assert utility.get_override_string_value_or_default(override, default) == expected


@pytest.mark.parametrize(
    ("override", "default", "expected"),
    [("5", 0, 5), (None, "7", 7), (None, None, None)],
)
def test_get_override_int_value_or_default_returns_expected_value(
    override, default, expected
):
    """
    Test that get_override_int_value_or_default prefers overrides then defaults.
    """
    assert utility.get_override_int_value_or_default(override, default) == expected


@pytest.mark.parametrize(
    ("override", "default", "expected"),
    [("5.5", None, 5.5), (None, "7.25", 7.25), (None, None, 0)],
)
def test_get_override_float_value_or_default_returns_expected_value(
    override, default, expected
):
    """
    Test that get_override_float_value_or_default prefers overrides then defaults.
    """
    assert utility.get_override_float_value_or_default(override, default) == expected


@pytest.mark.parametrize(
    ("override", "default", "expected"),
    [(True, None, 1), (False, True, 0), (None, True, 1), (None, None, 0)],
)
def test_get_override_tinyint_value_or_default_from_bool_returns_expected_value(
    override, default, expected
):
    """
    Test that get_override_tinyint_value_or_default_from_bool maps bools to tinyints.
    """
    assert (
        utility.get_override_tinyint_value_or_default_from_bool(override, default)
        == expected
    )


@pytest.mark.parametrize(
    ("override", "default", "expected"),
    [(1, None, True), (0, True, False), (None, 1, True), (None, None, False)],
)
def test_get_override_bool_value_or_default_returns_expected_value(
    override, default, expected
):
    """
    Test that get_override_bool_value_or_default maps numeric values to booleans.
    """
    assert utility.get_override_bool_value_or_default(override, default) is expected


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        (None, None),
        ("   ", None),
        ("(555) O12-oABC3:4 ", "555012034"),
    ],
)
def test_clean_up_phone_input_for_parsing_removes_noise(phone, expected):
    """
    Test that clean_up_phone_input_for_parsing removes formatting and letters.
    """
    assert utility.clean_up_phone_input_for_parsing(phone) == expected


def test_get_timezone_abbreviation_returns_none_for_none_timezone():
    """
    Test that get_timezone_abbreviation returns None without a timezone name.
    """
    assert utility.get_timezone_abbreviation(None) is None


def test_get_timezone_abbreviation_returns_fixed_date_abbreviation():
    """
    Test that get_timezone_abbreviation returns a timezone abbreviation for a date.
    """
    assert (
        utility.get_timezone_abbreviation("America/Los_Angeles", "2026-01-15") == "PST"
    )


def test_get_timezone_abbreviation_returns_current_abbreviation():
    """
    Test that get_timezone_abbreviation returns an abbreviation without a date.
    """
    assert utility.get_timezone_abbreviation("UTC") == "UTC"


def test_get_timezones_from_country_code_returns_timezone_models():
    """
    Test that get_timezones_from_country_code returns timezone models with labels.
    """
    timezones = utility.get_timezones_from_country_code("US", "2026-01-15")

    assert any(tz.timezone == "America/New_York" for tz in timezones)
    assert any(tz.display_name.startswith("America/New_York (") for tz in timezones)


def test_get_timezones_from_country_code_keeps_name_without_abbreviation(monkeypatch):
    """
    Test that get_timezones_from_country_code keeps the zone name without an abbreviation.
    """
    monkeypatch.setattr(
        utility, "get_timezone_abbreviation", lambda zone, time=None: None
    )

    timezones = utility.get_timezones_from_country_code("US", "2026-01-15")

    assert any(
        tz.timezone == "America/New_York" and tz.display_name == "America/New_York"
        for tz in timezones
    )


@pytest.mark.parametrize(
    ("zip_code", "expected"),
    [("90210", True), ("90210-1234", True), ("9021", False), ("abcde", False)],
)
def test_verify_usa_zip_code_validates_five_and_nine_digit_zip_codes(
    zip_code, expected
):
    """
    Test that verify_usa_zip_code accepts valid ZIP formats and rejects invalid ones.
    """
    assert utility.verify_usa_zip_code(zip_code) is expected


@pytest.mark.parametrize(
    ("state", "zip_code", "expected"),
    [
        ("CA", "90210", "USA"),
        ("ZZ", "90210", None),
        ("CA", "bad", None),
        (None, "90210", None),
    ],
)
def test_validate_usa_state_and_zip_returns_usa_for_valid_state_zip(
    state, zip_code, expected
):
    """
    Test that validate_usa_state_and_zip returns USA only for valid state/ZIP pairs.
    """
    assert utility.validate_usa_state_and_zip(state, zip_code) == expected


def test_get_country_from_country_name_returns_none_when_country_cannot_be_inferred():
    """
    Test that get_country_from_country_name returns None when no country can be inferred.
    """
    assert utility.get_country_from_country_name(None, "", "") is None


@pytest.mark.parametrize(
    ("country_name", "state", "zip_code", "queried_name"),
    [
        ("United States of America", "", "", "usa"),
        ("US", "", "", "usa"),
        ("England", "", "", "uk"),
        (None, "CA", "90210", "usa"),
    ],
)
def test_get_country_from_country_name_normalizes_names_before_query(
    monkeypatch, country_name, state, zip_code, queried_name
):
    """
    Test that get_country_from_country_name normalizes common country aliases.
    """
    calls = []

    def fake_db_query_one(sql, data):
        calls.append((sql, data))
        return {"CountryId": "1", "CountryName": "USA", "CountryCode": "US"}

    monkeypatch.setattr(utility, "db_query_one", fake_db_query_one)

    country = utility.get_country_from_country_name(country_name, state, zip_code)

    assert country.country_id == 1
    assert country.country_name == "USA"
    assert country.country_code == "US"
    assert calls[0][1] == {"country_name": queried_name}


def test_get_country_from_country_name_returns_none_when_db_has_no_row(monkeypatch):
    """
    Test that get_country_from_country_name returns None when the DB lookup is empty.
    """
    monkeypatch.setattr(utility, "db_query_one", lambda sql, data: {})

    assert utility.get_country_from_country_name("France", "", "") is None


def test_get_country_from_country_name_returns_none_when_country_code_is_missing(
    monkeypatch,
):
    """
    Test that get_country_from_country_name returns None without a DB country code.
    """
    monkeypatch.setattr(
        utility,
        "db_query_one",
        lambda sql, data: {
            "CountryId": 1,
            "CountryName": "France",
            "CountryCode": None,
        },
    )

    assert utility.get_country_from_country_name("France", "", "") is None


def test_get_country_from_country_id_uses_default_country_id(monkeypatch):
    """
    Test that get_country_from_country_id uses DEFAULT_COUNTRY_ID for missing ids.
    """
    calls = []
    monkeypatch.setenv("DEFAULT_COUNTRY_ID", "99")

    def fake_db_query_one(sql, data):
        calls.append((sql, data))
        return {"CountryId": "99", "CountryName": "USA", "CountryCode": "US"}

    monkeypatch.setattr(utility, "db_query_one", fake_db_query_one)

    country = utility.get_country_from_country_id(None)

    assert country.country_id == 99
    assert calls[0][1] == {"country_id": 99}


def test_get_country_from_country_id_returns_none_when_db_has_no_row(monkeypatch):
    """
    Test that get_country_from_country_id returns None when the DB lookup is empty.
    """
    monkeypatch.setattr(utility, "db_query_one", lambda sql, data: {})

    assert utility.get_country_from_country_id(1) is None


def test_get_country_from_country_id_returns_none_when_country_code_is_missing(
    monkeypatch,
):
    """
    Test that get_country_from_country_id returns None without a DB country code.
    """
    monkeypatch.setattr(
        utility,
        "db_query_one",
        lambda sql, data: {
            "CountryId": 1,
            "CountryName": "France",
            "CountryCode": None,
        },
    )

    assert utility.get_country_from_country_id(1) is None


@pytest.mark.parametrize(
    ("image_type", "env_name", "expected"),
    [
        (ImageType.HEADERS, "S3_BUCKET_HEADERS", "headers"),
        (ImageType.HOMEBANNERS, "S3_BUCKET_HOMEBANNERS", "homebanners"),
        (ImageType.LOGOS, "S3_BUCKET_LOGOS", "logos"),
        (ImageType.PREVIEWS, "S3_BUCKET_PREVIEW", "previews"),
        (ImageType.THUMBNAILS, "S3_BUCKET_THUMBNAILS", "thumbnails"),
        (ImageType.EVENT_THUMBNAILS, "S3_BUCKET_THUMBNAILS", "thumbnails"),
        (ImageType.FEATURED_ARTISTS, "S3_BUCKET_FEATURED_ARTISTS", "featured"),
    ],
)
def test_get_bucket_name_from_image_type_reads_expected_environment_variable(
    monkeypatch, image_type, env_name, expected
):
    """
    Test that get_bucket_name_from_image_type maps image types to bucket variables.
    """
    monkeypatch.setenv(env_name, expected)

    assert utility.get_bucket_name_from_image_type(image_type) == expected


def test_get_bucket_name_from_image_type_returns_none_for_unknown_type():
    """
    Test that get_bucket_name_from_image_type returns None for unknown image types.
    """
    assert utility.get_bucket_name_from_image_type("unknown") is None


@pytest.mark.parametrize(
    ("image_type", "expected"),
    [
        (ImageType.HEADERS, HEADER_IMAGE_WIDTH),
        (ImageType.HOMEBANNERS, HOMEBANNER_IMAGE_WIDTH),
        (ImageType.LOGOS, LOGO_IMAGE_WIDTH),
        (ImageType.PREVIEWS, PREVIEW_IMAGE_WIDTH),
        (ImageType.THUMBNAILS, THUMBNAIL_IMAGE_WIDTH),
        (ImageType.EVENT_THUMBNAILS, EVENT_THUMBNAIL_IMAGE_WIDTH),
        (ImageType.FEATURED_ARTISTS, FEATURED_ARTIST_IMAGE_WIDTH),
        ("unknown", 0),
    ],
)
def test_get_image_width_from_image_type_returns_expected_width(image_type, expected):
    """
    Test that get_image_width_from_image_type maps image types to configured widths.
    """
    assert utility.get_image_width_from_image_type(image_type) == expected


def test_get_pacific_purchase_date_from_order_converts_unix_timestamp():
    """
    Test that get_pacific_purchase_date_from_order converts UTC timestamps to Pacific dates.
    """
    order = TicketSocketOrder()
    order.purchase_unix_timestamp = 0
    order.purchase_date = "fallback"

    assert utility.get_pacific_purchase_date_from_order(order) == "fallback"

    order.purchase_unix_timestamp = 1

    assert utility.get_pacific_purchase_date_from_order(order) == "1969-12-31"


def test_get_pacific_purchase_timestamp_from_order_converts_unix_timestamp():
    """
    Test that get_pacific_purchase_timestamp_from_order converts UTC timestamps to Pacific timestamps.
    """
    order = TicketSocketOrder()
    order.purchase_unix_timestamp = 0
    order.purchase_timestamp = "fallback"

    assert utility.get_pacific_purchase_timestamp_from_order(order) == "fallback"

    order.purchase_unix_timestamp = 1

    assert (
        utility.get_pacific_purchase_timestamp_from_order(order)
        == "1969-12-31 16:00:01"
    )


def test_get_pacific_date_from_unix_timestamp_converts_to_pacific_date():
    """
    Test that get_pacific_date_from_unix_timestamp converts UTC timestamps to Pacific dates.
    """
    assert utility.get_pacific_date_from_unix_timestamp(1) == "1969-12-31"


def test_get_pacific_date_from_utc_string_converts_to_pacific_date():
    """
    Test that get_pacific_date_from_utc_string converts a UTC date string to a Pacific date.
    """
    assert utility.get_pacific_date_from_utc_string("2026-01-02") == "2026-01-01"


@pytest.mark.parametrize(
    ("utc_datetime_string", "expected"),
    [
        ("2026-01-02 07:30:00", "2026-01-01"),
        ("2026-01-02 08:00:00", "2026-01-02"),
        ("2026-07-02 06:30:00", "2026-07-01"),
        ("2026-07-02 07:00:00", "2026-07-02"),
    ],
)
def test_get_pacific_date_from_utc_datetime_string_converts_to_pacific_date(
    utc_datetime_string, expected
):
    """
    Test that get_pacific_date_from_utc_datetime_string respects UTC input and Pacific DST.
    """
    assert (
        utility.get_pacific_date_from_utc_datetime_string(utc_datetime_string)
        == expected
    )
