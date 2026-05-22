"""
Exchange Rate
"""


class ExchangeRate:
    """
    Class representation of an exchange rate
    """

    usd_rate: float = 1.0
    multiplier: float = 1.0

    def __init__(
        self,
        exchange_rate_id: int,
        exchange_rate_slug: str,
        currency_symbol: str,
    ):
        self.exchange_rate_id = exchange_rate_id
        self.exchange_rate_slug = exchange_rate_slug
        self.currency_symbol = currency_symbol
