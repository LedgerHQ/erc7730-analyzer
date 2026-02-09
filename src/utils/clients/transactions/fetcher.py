"""Public transaction fetcher composed from focused mixins."""

from .core import TransactionFetcherCoreMixin
from .decoding import TransactionFetcherDecodingMixin
from .receipts import TransactionFetcherReceiptMixin


class TransactionFetcher(
    TransactionFetcherCoreMixin,
    TransactionFetcherReceiptMixin,
    TransactionFetcherDecodingMixin,
):
    """Composite transaction fetcher."""

    pass
