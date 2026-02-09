"""Composed core transaction mixin from focused stages."""

from .aggregation import TransactionFetcherCoreAggregationMixin
from .base import TransactionFetcherCoreBaseMixin
from .explorers import TransactionFetcherCoreExplorerMixin
from .query import TransactionFetcherCoreQueryMixin


class TransactionFetcherCoreMixin(
    TransactionFetcherCoreBaseMixin,
    TransactionFetcherCoreExplorerMixin,
    TransactionFetcherCoreAggregationMixin,
    TransactionFetcherCoreQueryMixin,
):
    """Composite core transaction mixin."""

    pass
