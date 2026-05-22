"""
Models for Twilio/SendGrid
"""


class SendEmailResult:
    """
    Class for sending email
    """

    def __init__(self, success: bool, error: str = None):
        self.success = success
        self.error = error
