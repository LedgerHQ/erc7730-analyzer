"""Composed core transaction mixin from focused stages."""

from .aggregation import TransactionFetcherCoreAggregationMixin
from .base import TransactionFetcherCoreBaseMixin
from .explorers import TransactionFetcherCoreExplorerMixin
from .query import TransactionFetcherCoreQueryMixin
from .snowflake import TransactionFetcherCoreSnowflakeMixin


class TransactionFetcherCoreMixin(
    TransactionFetcherCoreBaseMixin,
    TransactionFetcherCoreExplorerMixin,
    TransactionFetcherCoreSnowflakeMixin,
    TransactionFetcherCoreAggregationMixin,
    TransactionFetcherCoreQueryMixin,
):
    """Composite core transaction mixin."""

    pass
