"""
Public service module
"""

import os
import traceback
import logging
from flask import Request
from common.db import db_query_all
from common.models.admin import FeaturedArtist
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    resize_and_move_temp_file_to_s3,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PublicService:
    """
    Service to handle miscellaneous functions from public routes
    """

    def upload_image_to_bucket(
        self, request: Request, bucket_name: str, max_width: int
    ) -> str:
        """
        Uploads a file to the specified S3 bucket
        """
        filename: str = None
        try:
            # save to temp folder first
            file = request.files["tempFile"]
            temp_filename = file.filename

            # replace garbage characters from Windows/Mac
            temp_filename = temp_filename.replace(" ", "_")
            temp_filename = temp_filename.replace("(", "_")
            temp_filename = temp_filename.replace(")", "_")
            temp_filename = temp_filename.replace("__", "_")

            api_path = os.getenv("API_FILE_PATH")
            temp_dir = os.path.join(api_path, "tmp")
            save_path = os.path.join(temp_dir, temp_filename)

            file.save(save_path)

            if not os.path.exists(save_path):
                logger.error("Temp file did not save correctly: %s", save_path)
                return None

            is_png = temp_filename.endswith(".png")

            filename = resize_and_move_temp_file_to_s3(
                temp_filename, bucket_name, max_width, is_png
            )

        except Exception as error:  # pylint: disable=broad-exception-caught
            filename = None
            error_message: str = str(error) + "\n" + traceback.format_exc()
            logger.error("%s", error_message)

        return filename

    def get_featured_artists(self):
        """
        Get featured artists
        """
        artists: list[FeaturedArtist] = []

        sql = """
            SELECT FeaturedArtists.*,
            Sellers.Name, 
            Pages.LinkPreviewImage,
            Pages.LogoOnly,
            Pages.Route
            FROM FeaturedArtists
            JOIN PageSellers ON FeaturedArtists.PageSellerId = PageSellers.PageSellerId
            JOIN Sellers ON PageSellers.SellerId = Sellers.SellerId
            JOIN Pages ON PageSellers.PageId = Pages.PageId
            ORDER BY FeaturedArtists.FeaturedArtistOrder
        """

        rows = db_query_all(sql)
        for row in rows:
            artist = FeaturedArtist(
                featured_artist_id=get_override_int_value_or_default(
                    row["FeaturedArtistId"]
                ),
                featured_artist_order=get_override_int_value_or_default(
                    row["FeaturedArtistOrder"]
                ),
                page_seller_id=get_override_int_value_or_default(row["PageSellerId"]),
                title=get_override_string_value_or_default(row["Name"]),
                background_image=get_override_string_value_or_default(
                    row["BackgroundImage"]
                ),
                preview_image=get_override_string_value_or_default(
                    row["LinkPreviewImage"]
                ),
                logo_image=get_override_string_value_or_default(row["LogoOnly"]),
                href=get_override_string_value_or_default(row["Route"]),
            )
            artists.append(artist)

        return artists
