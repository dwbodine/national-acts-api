"""
Service to manage fan moment photos in S3.
"""

import mimetypes
import os
import logging
import traceback
from typing import Any

import boto3

from common.event_service import EventService
from common.models.admin import FanMoment, FanMomentKey
from common.models.national_acts import Seller, VipEvent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MomentsService:
    """
    Service to handle fan moment photo S3 activity.
    """

    def filter_moments(
        self, moment_date: str = None, seller_id: int = None, event_id: int = None
    ) -> list[FanMoment]:
        """
        Get fan moment photo objects from the moments S3 bucket by filter criteria.
        """
        s3_keys = self._list_keys(
            self._build_filter_prefix(moment_date, seller_id, event_id)
        )

        moments: list[FanMoment] = []
        seller_names_by_id: dict[int, str] = {}
        event_details_by_id: dict[int, tuple[str, str]] = {}
        event_service = EventService()
        
        current_fm_key: FanMomentKey = None
        
        for s3_key in s3_keys:
            fm_key = self._parse_fan_moment_key(s3_key)
            if fm_key is None or not self._is_parsed_moment_match(
                fm_key, moment_date, seller_id, event_id
            ):
                continue
            
            if current_fm_key is None:
                current_fm_key = fm_key
            elif current_fm_key.str() != fm_key.str():
                
                

            seller_name: str = None
            if seller_id_parsed is not None:
                if seller_id_parsed not in seller_names_by_id:
                    seller = Seller(seller_id_parsed, get_event_categories=False)
                    seller_names_by_id[seller_id_parsed] = (
                        seller.name if seller is not None else None
                    )
                seller_name = seller_names_by_id[seller_id_parsed]
            
            event_title: str = None
            event_location: str = None
            if event_id_parsed is not None:
                if event_id_parsed not in event_details_by_id:
                    evt_list = event_service.get_events_and_orders(
                        event_id=event_id_parsed, get_orders=False, is_public=True
                    )
                    if evt_list is not None and len(evt_list) > 0:
                        event_details_by_id[event_id_parsed] = (
                            evt_list[0].title,
                            event_service.get_location_from_event(evt_list[0]),
                        )
                    else:
                        event_details_by_id[event_id_parsed] = (None, None)
                event_title, event_location = event_details_by_id[event_id_parsed]

            moments.append(
                FanMoment(
                    moment_date=moment_date_parsed,
                    seller_id=seller_id_parsed,
                    seller_name=seller_name,
                    event_id=event_id_parsed,
                    event_title=event_title,
                    event_location=event_location,
                    url=f"{os.getenv("S3_BUCKET_MOMENTS")}/{key}",
                )
            )

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

    def add_moments(
        self, moment_date: str, seller_id: int, event_id: int, filenames: list[str]
    ) -> list[str]:
        """
        Add photos to the moments S3 bucket.
        """
        if filenames is None:
            return []

        uploaded_keys: list[str] = []
        bucket_name = self._get_bucket_name()
        if bucket_name is None:
            return uploaded_keys

        prefix = self._build_event_prefix(moment_date, seller_id, event_id)
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

    def delete_moments(
        self, moment_date: str, seller_id: int, event_id: int, filenames: list[str]
    ) -> list[str]:
        """
        Delete photos from the moments S3 bucket.
        """
        if filenames is None:
            return []

        deleted_keys: list[str] = []
        bucket_name = self._get_bucket_name()
        if bucket_name is None:
            return deleted_keys

        prefix = self._build_event_prefix(moment_date, seller_id, event_id)
        objects = [
            {"Key": f"{prefix}{os.path.basename(filename)}"} for filename in filenames
        ]
        s3_client = boto3.client("s3")

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

        return deleted_keys

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
        for key in self._list_keys():
            parsed = self._parse_moment_key(key)
            if parsed is not None and parsed["seller_id"] == seller_id:
                dates.add(parsed["moment_date"])

        return sorted(dates)

    def get_available_moment_sellers(self, moment_date: str = None) -> list[Seller]:
        """
        Get all available moment sellers, possibly filtered by date
        """
        seller_ids = set()
        if moment_date is not None:
            for prefix in self._list_common_prefixes(f"{moment_date}/"):
                seller_id = self._try_parse_int(self._last_prefix_segment(prefix))
                if seller_id is not None:
                    seller_ids.add(seller_id)
            return self._get_sellers_from_ids(seller_ids)

        for key in self._list_keys():
            parsed = self._parse_moment_key(key)
            if parsed is not None:
                seller_ids.add(parsed["seller_id"])

        return self._get_sellers_from_ids(seller_ids)

    def get_available_moment_events(
        self, moment_date: str = None, seller_id: int = None
    ) -> list[VipEvent]:
        """
        Get all available moment events, possibly filtered by date and/or seller id
        """
        event_ids = set()
        if moment_date is not None and seller_id is not None:
            prefix = f"{moment_date}/{seller_id}/"
            for common_prefix in self._list_common_prefixes(prefix):
                event_id = self._try_parse_int(self._last_prefix_segment(common_prefix))
                if event_id is not None:
                    event_ids.add(event_id)
            return self._get_events_from_ids(event_ids)

        keys = self._list_keys(f"{moment_date}/" if moment_date is not None else "")
        for key in keys:
            parsed = self._parse_moment_key(key)
            if parsed is None:
                continue
            if seller_id is not None and parsed["seller_id"] != seller_id:
                continue
            event_ids.add(parsed["event_id"])

        return self._get_events_from_ids(event_ids)

    def _get_bucket_name(self) -> str:
        """
        Get the moments S3 bucket name from environment settings.
        """
        bucket_name = os.getenv("S3_BUCKET_MOMENTS")
        if bucket_name is None or len(bucket_name.strip()) == 0:
            logger.error("S3_BUCKET_MOMENTS is not configured")
            return None
        return bucket_name.strip()

    def _build_event_prefix(
        self, moment_date: str, seller_id: int, event_id: int
    ) -> str:
        """
        Build the S3 prefix for one moment event.
        """
        return f"{moment_date}/{seller_id}/{event_id}/"

    def _build_filter_prefix(
        self, moment_date: str = None, seller_id: int = None, event_id: int = None
    ) -> str:
        """
        Build the narrowest contiguous S3 prefix available from the filter values.
        """
        if moment_date is None:
            return ""
        if seller_id is None:
            return f"{moment_date}/"
        if event_id is None:
            return f"{moment_date}/{seller_id}/"
        return self._build_event_prefix(moment_date, seller_id, event_id)

    def _list_keys(self, prefix: str = "") -> list[str]:
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
                        if not obj["Key"].endswith("/")
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
        if len(segments) < 4 or len(segments[3]) == 0:
            return None

        seller_id = self._try_parse_int(segments[1])
        event_id = self._try_parse_int(segments[2])
        if (
            not self._is_valid_date_folder(segments[0])
            or seller_id is None
            or event_id is None
        ):
            return None

        return FanMomentKey(
            moment_date=segments[0],
            seller_id=seller_id,
            event_id=event_id,
            filename="/".join(segments[3:]),
        )

    def _is_moment_key_match(
        self,
        key: str,
        moment_date: str = None,
        seller_id: int = None,
        event_id: int = None,
    ) -> bool:
        """
        Determine whether a key matches the supplied filters.
        """
        parsed = self._parse_moment_key(key)
        if parsed is None:
            return False
        return self._is_parsed_moment_match(parsed, moment_date, seller_id, event_id)

    def _is_parsed_moment_match(
        self,
        key: FanMomentKey,
        moment_date: str = None,
        seller_id: int = None,
        event_id: int = None,
    ) -> bool:
        """
        Determine whether parsed moment key data matches the supplied filters.
        """
        if moment_date is not None and key.moment_date != moment_date:
            return False
        if seller_id is not None and key.seller_id != seller_id:
            return False
        if event_id is not None and key.event_id != event_id:
            return False
        return True

    def _is_valid_date_folder(self, folder: str) -> bool:
        """
        Determine whether a folder name is shaped like YYYY-MM-DD.
        """
        if folder is None or len(folder) != 10:
            return False
        return folder[4] == "-" and folder[7] == "-"

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
