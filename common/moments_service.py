"""
Service to manage fan moment photos in S3.
"""

import mimetypes
import os
import logging
import traceback

import boto3

from common.event_service import EventService
from common.models.admin import FanMoment, FanMomentEvent, FanMomentKey
from common.models.national_acts import Seller, VipEvent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MomentsService:
    """
    Service to handle fan moment photo S3 activity.
    """

    def filter_moments(
        self,
        start_date: str = None,
        end_date: str = None,
        seller_id: int = None,
        event_id: int = None,
    ) -> list[FanMoment]:
        """
        Get fan moment photo objects from the moments S3 bucket by filter criteria.
        """
        is_unfiltered = (
            start_date is None
            and end_date is None
            and seller_id is None
            and event_id is None
        )
        moments: list[FanMoment] = []
        seller_names_by_id: dict[int, str] = {}
        event_details_by_id: dict[int, tuple[int, str, str]] = {}
        event_service = EventService()

        if event_id is not None:
            start_date = None
            end_date = None
            seller_id = None
        elif seller_id is not None:
            start_date = None
            end_date = None

        if seller_id is not None:
            self._prefill_event_details_by_seller(
                seller_id, event_service, event_details_by_id
            )

        matching_prefixes = self._list_matching_event_prefixes(
            start_date, end_date, event_id
        )
        if seller_id is not None:
            matching_prefixes = self._filter_event_prefixes_to_known_events(
                matching_prefixes, event_details_by_id
            )

        for event_prefix in matching_prefixes:
            fm_key = self._parse_fan_moment_prefix(event_prefix)
            if fm_key is None:
                continue

            event_seller_id, event_title, event_location = self._get_event_details(
                fm_key.event_id, event_service, event_details_by_id
            )
            fm_key.seller_id = event_seller_id

            if not self._is_parsed_moment_match(
                fm_key, start_date, end_date, seller_id, event_id
            ):
                continue

            images = self._list_moment_images(event_prefix)
            if len(images) == 0:
                continue

            seller_name: str = None
            if fm_key.seller_id is not None:
                if fm_key.seller_id not in seller_names_by_id:
                    seller = Seller(fm_key.seller_id, get_event_categories=False)
                    seller_names_by_id[fm_key.seller_id] = (
                        seller.name if seller is not None else None
                    )
                seller_name = seller_names_by_id[fm_key.seller_id]

            fm_key.seller_name = seller_name
            fm_key.event_title = event_title
            fm_key.event_location = event_location
            moment = FanMoment()
            moment.key = fm_key
            moment.images = images
            moments.append(moment)

        if is_unfiltered:
            return self._sort_recent_moments(moments)[:8]

        return self._sort_moments(moments)

    def _sort_moments(self, moments: list[FanMoment]) -> list[FanMoment]:
        """
        Sort fan moments by date, seller name, and event title.
        """
        return sorted(
            moments,
            key=lambda moment: (
                moment.moment_date is None,
                moment.moment_date or "",
                moment.seller_name is None,
                moment.seller_name.lower() if moment.seller_name is not None else "",
                moment.event_title is None,
                moment.event_title.lower() if moment.event_title is not None else "",
            ),
        )

    def _sort_recent_moments(self, moments: list[FanMoment]) -> list[FanMoment]:
        """
        Sort fan moments from newest to oldest moment date.
        """
        return sorted(
            moments,
            key=lambda moment: (
                moment.moment_date or "",
                moment.seller_name is None,
                moment.seller_name.lower() if moment.seller_name is not None else "",
                moment.event_title is None,
                moment.event_title.lower() if moment.event_title is not None else "",
            ),
            reverse=True,
        )

    def add_moments(self, fm_key: FanMomentKey, filenames: list[str]) -> list[str]:
        """
        Add photos to the moments S3 bucket.
        """
        if filenames is None:
            return []

        uploaded_keys: list[str] = []
        bucket_name = self._get_bucket_name()
        if bucket_name is None:
            return uploaded_keys

        prefix = self._build_event_prefix(fm_key.moment_date, fm_key.event_id)
        s3_client = boto3.client("s3")

        for filename in filenames:
            upload_path = self._get_upload_path(filename)
            if upload_path is None:
                logger.error("add_moments - file does not exist: %s", filename)
                continue

            object_name = os.path.basename(upload_path)
            key = f"{prefix}{object_name}"
            extra_args = self._get_upload_extra_args(object_name)

            try:
                s3_client.upload_file(
                    upload_path, bucket_name, key, ExtraArgs=extra_args
                )
                uploaded_keys.append(key)
            except Exception as error:  # pylint: disable=broad-exception-caught
                error_message: str = str(error) + "\n" + traceback.format_exc()
                logger.error("%s", error_message)

        return uploaded_keys

    def moment_exists(self, moment_date: str, event_id: int, filename: str) -> bool:
        """
        Check whether a moment photo exists in S3.
        """
        event_prefix = self._build_event_prefix(moment_date, event_id)
        expected_key = f"{event_prefix}{filename}"
        keys = self._list_keys(event_prefix)
        return expected_key in keys

    def update_moment(self, fm: FanMoment) -> bool:
        """
        Delete unused moment photos in the moments S3 bucket on finalize
        """
        if fm is None or fm.key is None or fm.images is None or len(fm.images) == 0:
            return None

        fm_key = fm.key
        filenames = fm.images

        if fm_key is None or fm_key.moment_date is None or fm_key.event_id is None:
            return None

        existing_moment = self.get_moment(fm_key)
        if existing_moment is None or existing_moment.images is None:
            return None

        delete_filenames: list[str] = []
        for filename in existing_moment.images:
            if filename not in filenames:
                delete_filenames.append(filename)

        success = True
        if len(delete_filenames) > 0:
            success = self._delete_moment_images(fm_key, delete_filenames)

        return success

    def get_moment(self, fm_key: FanMomentKey) -> FanMoment | None:
        """
        Get a single fan moment photo object from the moments S3 bucket.
        """
        if fm_key is None or fm_key.moment_date is None or fm_key.event_id is None:
            return None

        prefix = self._build_event_prefix(fm_key.moment_date, fm_key.event_id)
        moment = FanMoment()
        moment.key = fm_key
        moment.images = self._list_moment_images(prefix)
        return moment

    def delete_moments(self, fm_key: FanMomentKey) -> bool:
        """
        Delete the moment folder from the S3 bucket.
        """
        if fm_key is None or fm_key.moment_date is None or fm_key.event_id is None:
            return False

        prefix = self._build_event_prefix(fm_key.moment_date, fm_key.event_id)
        keys = self._list_keys(prefix, include_folder_markers=True)
        if self._delete_keys(keys) is False:
            return False

        date_prefix = f"{fm_key.moment_date}/"
        remaining_date_keys = self._list_keys(date_prefix, include_folder_markers=True)
        if remaining_date_keys == [date_prefix]:
            return self._delete_keys([date_prefix])

        return True

    def _delete_moment_images(self, fm_key: FanMomentKey, filenames: list[str]) -> bool:
        """
        Delete selected image keys from one moment event prefix.
        """
        if (
            fm_key is None
            or fm_key.moment_date is None
            or fm_key.event_id is None
            or filenames is None
        ):
            return []

        prefix = self._build_event_prefix(fm_key.moment_date, fm_key.event_id)
        keys: list[str] = []
        for filename in filenames:
            if filename is None or len(str(filename).strip()) == 0:
                continue
            normalized_filename = str(filename).replace("\\", "/").lstrip("/")
            keys.append(f"{prefix}{normalized_filename}")
        return self._delete_keys(keys)

    def _delete_keys(self, keys: list[str]) -> bool:
        """
        Delete S3 object keys from the moments bucket in batches.
        """
        deleted_keys: list[str] = []
        if keys is None or len(keys) == 0:
            return False

        bucket_name = self._get_bucket_name()
        if bucket_name is None:
            return False

        s3_client = boto3.client("s3")
        objects = [{"Key": key} for key in keys]

        success = True
        for index in range(0, len(objects), 1000):
            batch = objects[index : index + 1000]
            try:
                response = s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={"Objects": batch, "Quiet": True},
                )
                deleted = response.get("Deleted", batch)
                deleted_keys.extend([item["Key"] for item in deleted])
            except Exception as error:  # pylint: disable=broad-exception-caught
                error_message: str = str(error) + "\n" + traceback.format_exc()
                logger.error("%s", error_message)
                success = False
                break

        return success

    def get_available_moment_dates(self, seller_id: int = None) -> list[str]:
        """
        Get all available moment dates, possibly filtered by seller id
        """
        if seller_id is None:
            dates = [
                prefix.strip("/")
                for prefix in self._list_common_prefixes()
                if self._is_valid_date_folder(prefix.strip("/"))
            ]
            return sorted(dates)

        dates = set()
        event_details_by_id: dict[int, tuple[int, str, str]] = {}
        event_service = EventService()
        for key in self._list_keys():
            fm_key = self._parse_fan_moment_key(key)
            if fm_key is None:
                continue
            event_seller_id, _event_title, _event_location = self._get_event_details(
                fm_key.event_id, event_service, event_details_by_id
            )
            if event_seller_id == seller_id:
                dates.add(fm_key.moment_date)

        return sorted(dates)

    def get_available_moment_sellers(self, moment_date: str = None) -> list[Seller]:
        """
        Get all available moment sellers, possibly filtered by date
        """
        seller_ids = set()
        event_details_by_id: dict[int, tuple[int, str, str]] = {}
        event_service = EventService()
        for key in self._list_keys(
            f"{moment_date}/" if moment_date is not None else ""
        ):
            fm_key = self._parse_fan_moment_key(key)
            if fm_key is not None:
                event_seller_id, _event_title, _event_location = (
                    self._get_event_details(
                        fm_key.event_id, event_service, event_details_by_id
                    )
                )
                if event_seller_id is not None:
                    seller_ids.add(event_seller_id)

        return self._get_sellers_from_ids(seller_ids)

    def get_available_moment_events(
        self, moment_date: str = None, seller_id: int = None
    ) -> list[FanMomentEvent]:
        """
        Get all available moment events, possibly filtered by date and/or seller id.
        """
        event_ids: set[int] = set()
        keys = self._list_keys(f"{moment_date}/" if moment_date is not None else "")
        event_details_by_id: dict[int, tuple[int, str, str]] = {}
        event_service = EventService()
        for key in keys:
            fm_key = self._parse_fan_moment_key(key)
            if fm_key is None:
                continue
            event_seller_id, _event_title, _event_location = self._get_event_details(
                fm_key.event_id, event_service, event_details_by_id
            )
            if seller_id is not None and event_seller_id != seller_id:
                continue
            event_ids.add(fm_key.event_id)

        return [
            FanMomentEvent(event_id, event_details_by_id[event_id][2])
            for event_id in sorted(event_ids)
        ]

    def _get_bucket_name(self) -> str:
        """
        Get the moments S3 bucket name from environment settings.
        """
        bucket_name = os.getenv("S3_BUCKET_MOMENTS")
        if bucket_name is None or len(bucket_name.strip()) == 0:
            logger.error("S3_BUCKET_MOMENTS is not configured")
            return None
        return bucket_name.strip()

    def _build_event_prefix(self, moment_date: str, event_id: int) -> str:
        """
        Build the S3 prefix for one moment event.
        """
        return f"{moment_date}/{event_id}/"

    def _build_filter_prefix(
        self,
        start_date: str = None,
        end_date: str = None,
        event_id: int = None,
    ) -> str:
        """
        Build the narrowest contiguous S3 prefix available from the filter values.
        """
        if event_id is not None:
            return ""
        if start_date is None or start_date != end_date:
            return ""
        return f"{start_date}/"

    def _list_keys(
        self, prefix: str = "", include_folder_markers: bool = False
    ) -> list[str]:
        """
        List all S3 object keys under a prefix.
        """
        bucket_name = self._get_bucket_name()
        if bucket_name is None:
            return []

        keys: list[str] = []
        s3_client = boto3.client("s3")
        kwargs = {"Bucket": bucket_name, "Prefix": prefix}

        try:
            while True:
                response = s3_client.list_objects_v2(**kwargs)
                keys.extend(
                    [
                        obj["Key"]
                        for obj in response.get("Contents", [])
                        if include_folder_markers or not obj["Key"].endswith("/")
                    ]
                )
                if response.get("IsTruncated") is not True:
                    break
                kwargs["ContinuationToken"] = response.get("NextContinuationToken")
        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            logger.error("%s", error_message)
            return []

        return sorted(keys)

    def _list_common_prefixes(self, prefix: str = "") -> list[str]:
        """
        List direct child prefixes under an S3 prefix.
        """
        bucket_name = self._get_bucket_name()
        if bucket_name is None:
            return []

        prefixes: list[str] = []
        s3_client = boto3.client("s3")
        kwargs = {"Bucket": bucket_name, "Prefix": prefix, "Delimiter": "/"}

        try:
            while True:
                response = s3_client.list_objects_v2(**kwargs)
                prefixes.extend(
                    [
                        item["Prefix"]
                        for item in response.get("CommonPrefixes", [])
                        if item.get("Prefix") is not None
                    ]
                )
                if response.get("IsTruncated") is not True:
                    break
                kwargs["ContinuationToken"] = response.get("NextContinuationToken")
        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            logger.error("%s", error_message)
            return []

        return sorted(prefixes)

    def _list_matching_event_prefixes(
        self, start_date: str = None, end_date: str = None, event_id: int = None
    ) -> list[str]:
        """
        List event-level prefixes that can satisfy the supplied date/event filters.
        """
        date_prefixes = self._list_candidate_date_prefixes(
            start_date, end_date, event_id
        )
        event_prefixes: list[str] = []

        for date_prefix in date_prefixes:
            moment_date = date_prefix.strip("/")
            if not self._is_valid_date_folder(moment_date):
                continue
            if event_id is None and not self._is_moment_date_match(
                moment_date, start_date, end_date
            ):
                continue
            if event_id is not None:
                event_prefixes.append(self._build_event_prefix(moment_date, event_id))
                continue
            event_prefixes.extend(self._list_common_prefixes(date_prefix))

        return sorted(event_prefixes)

    def _list_candidate_date_prefixes(
        self, start_date: str = None, end_date: str = None, event_id: int = None
    ) -> list[str]:
        """
        List date-level prefixes worth inspecting for the supplied filters.
        """
        if event_id is None and start_date is not None and start_date == end_date:
            return [f"{start_date}/"]
        return self._list_common_prefixes()

    def _list_moment_images(self, event_prefix: str) -> list[str]:
        """
        List image filenames inside an event-level moment prefix.
        """
        images: list[str] = []
        for s3_key in self._list_keys(event_prefix):
            fm_key = self._parse_fan_moment_key(s3_key)
            if fm_key is not None:
                images.append(fm_key.filename)
        return images

    def _get_upload_path(self, filename: str) -> str:
        """
        Resolve a filename to a local upload path.
        """
        if filename is None or len(str(filename).strip()) == 0:
            return None

        if os.path.exists(filename):
            return filename

        api_path = os.getenv("API_FILE_PATH")
        if api_path is not None:
            temp_path = os.path.join(api_path, "tmp", filename)
            if os.name == "nt" and len(temp_path) > 0:
                temp_path = temp_path.replace("/", "\\")
            if os.path.exists(temp_path):
                return temp_path

        return None

    def _get_upload_extra_args(self, filename: str) -> dict[str, str]:
        """
        Get S3 upload metadata for a photo.
        """
        content_type = mimetypes.guess_type(filename)[0]
        if content_type is None:
            content_type = "application/octet-stream"
        return {"ContentType": content_type}

    def _parse_fan_moment_key(self, key: str) -> FanMomentKey | None:
        """
        Parse a moment S3 object key into its folder components.
        """
        segments = key.split("/")
        if len(segments) < 3 or len(segments[2]) == 0:
            return None

        event_id = self._try_parse_int(segments[1])
        if not self._is_valid_date_folder(segments[0]) or event_id is None:
            return None

        fm_key = FanMomentKey()
        fm_key.moment_date = segments[0]
        fm_key.seller_id = None
        fm_key.event_id = event_id
        fm_key.filename = "/".join(segments[2:])
        return fm_key

    def _parse_fan_moment_prefix(self, prefix: str) -> FanMomentKey | None:
        """
        Parse a moment S3 event prefix into its date and event folder components.
        """
        segments = prefix.strip("/").split("/")
        if len(segments) != 2:
            return None

        event_id = self._try_parse_int(segments[1])
        if not self._is_valid_date_folder(segments[0]) or event_id is None:
            return None

        fm_key = FanMomentKey()
        fm_key.moment_date = segments[0]
        fm_key.seller_id = None
        fm_key.event_id = event_id
        return fm_key

    def _is_moment_key_match(
        self,
        key: str,
        start_date: str = None,
        end_date: str = None,
        seller_id: int = None,
        event_id: int = None,
    ) -> bool:
        """
        Determine whether a key matches the supplied filters.
        """
        fm_key = self._parse_fan_moment_key(key)
        if fm_key is None:
            return False
        if seller_id is not None and event_id is None:
            event_seller_id, _event_title, _event_location = self._get_event_details(
                fm_key.event_id, EventService(), {}
            )
            fm_key.seller_id = event_seller_id
        return self._is_parsed_moment_match(
            fm_key, start_date, end_date, seller_id, event_id
        )

    def _is_parsed_moment_match(
        self,
        key: FanMomentKey,
        start_date: str = None,
        end_date: str = None,
        seller_id: int = None,
        event_id: int = None,
    ) -> bool:
        """
        Determine whether parsed moment key data matches the supplied filters.
        """
        if event_id is not None:
            return key.event_id == event_id
        if seller_id is not None:
            return key.seller_id == seller_id
        if start_date is not None and (
            key.moment_date is None or key.moment_date < start_date
        ):
            return False
        if end_date is not None and (
            key.moment_date is None or key.moment_date > end_date
        ):
            return False
        return True

    def _is_valid_date_folder(self, folder: str) -> bool:
        """
        Determine whether a folder name is shaped like YYYY-MM-DD.
        """
        if folder is None or len(folder) != 10:
            return False
        return folder[4] == "-" and folder[7] == "-"

    def _is_moment_date_match(
        self, moment_date: str, start_date: str = None, end_date: str = None
    ) -> bool:
        """
        Determine whether a moment date folder matches the supplied date range.
        """
        if start_date is not None and (moment_date is None or moment_date < start_date):
            return False
        if end_date is not None and (moment_date is None or moment_date > end_date):
            return False
        return True

    def _try_parse_int(self, value: str) -> int:
        """
        Parse an int value, returning None for invalid input.
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _last_prefix_segment(self, prefix: str) -> str:
        """
        Get the last folder segment from an S3 common prefix.
        """
        return prefix.strip("/").split("/")[-1]

    def _get_event_details(
        self,
        event_id: int,
        event_service: EventService,
        event_details_by_id: dict[int, tuple[int, str, str]],
    ) -> tuple[int, str, str]:
        """
        Get seller id, title, and location for an event, cached by event id.
        """
        if event_id is None:
            return (None, None, None)
        if event_id not in event_details_by_id:
            evt_list = event_service.get_events_and_orders(
                event_id=event_id, get_orders=False, is_public=False
            )
            if evt_list is not None and len(evt_list) > 0:
                evt = evt_list[0]
                event_details_by_id[event_id] = (
                    getattr(evt, "seller_id", None),
                    getattr(evt, "title", None),
                    event_service.get_location_from_event(evt),
                )
            else:
                event_details_by_id[event_id] = (None, None, None)
        return event_details_by_id[event_id]

    def _prefill_event_details_by_seller(
        self,
        seller_id: int,
        event_service: EventService,
        event_details_by_id: dict[int, tuple[int, str, str]],
    ) -> None:
        """
        Cache seller event details before filtering S3 event prefixes.
        """
        events = event_service.get_events_and_orders(
            seller_id=seller_id, get_orders=False, is_public=False, ignore_flags=True
        )
        if events is None:
            return

        for evt in events:
            event_id = getattr(evt, "external_event_id", None)
            if event_id is None:
                event_id = getattr(evt, "event_id", None)
            if event_id is None:
                event_id = getattr(evt, "id", None)
            if event_id is None:
                continue

            event_details_by_id[event_id] = (
                getattr(evt, "seller_id", None),
                getattr(evt, "title", None),
                event_service.get_location_from_event(evt),
            )

    def _filter_event_prefixes_to_known_events(
        self,
        event_prefixes: list[str],
        event_details_by_id: dict[int, tuple[int, str, str]],
    ) -> list[str]:
        """
        Keep only event prefixes whose event id is already cached.
        """
        matching_prefixes: list[str] = []
        for event_prefix in event_prefixes:
            fm_key = self._parse_fan_moment_prefix(event_prefix)
            if fm_key is not None and fm_key.event_id in event_details_by_id:
                matching_prefixes.append(event_prefix)
        return matching_prefixes

    def _get_sellers_from_ids(self, seller_ids: set[int]) -> list[Seller]:
        """
        Hydrate seller ids and sort them by seller name.
        """
        sellers = [
            Seller(seller_id=seller_id, get_event_categories=False)
            for seller_id in seller_ids
        ]
        return sorted(
            sellers,
            key=lambda seller: (
                seller.name is None,
                seller.name.lower() if seller.name is not None else "",
                seller.seller_id,
            ),
        )

    def _get_events_from_ids(self, event_ids: set[int]) -> list[VipEvent]:
        """
        Hydrate event ids and sort them by event date and title.
        """
        events: list[VipEvent] = []
        event_service = EventService()
        for event_id in event_ids:
            evt = event_service.get_events_and_orders(
                get_orders=False, event_id=event_id, is_public=True
            )
            if evt is not None and len(evt) > 0:
                events.append(evt[0])

        return sorted(
            events,
            key=lambda evt: (
                evt.event_date is None,
                evt.event_date or "",
                evt.title is None,
                evt.title.lower() if evt.title is not None else "",
            ),
        )
