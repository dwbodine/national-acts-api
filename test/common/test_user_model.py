"""
Unit tests for user model helpers.
"""

from common.models.user import UserResponse


def test_user_response_has_error_when_error_message_is_present():
    """
    Test that UserResponse.has_error() returns True when an error message is present.
    """
    response = UserResponse(None, "Something went wrong")

    assert response.has_error() is True


def test_user_response_has_no_error_when_error_message_is_blank():
    """
    Test that UserResponse.has_error() returns False when the error message is blank.
    """
    response = UserResponse(None, "")

    assert response.has_error() is False
