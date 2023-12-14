class ExchangeRate:
    usdRate: float = 1.0

    def __init__(self, exchangeRateId: int, exchangeRateSlug: str, multiplier: float):
        self.exchangeRateId = exchangeRateId
        self.exchangeRateSlug = exchangeRateSlug
        self.multiplier = multiplier