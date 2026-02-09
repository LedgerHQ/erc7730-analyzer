"""Composed source fetching mixin from focused fetching stages."""

from .base import SourceCodeFetchingBaseMixin
from .extraction import SourceCodeFetchingExtractionMixin
from .providers import SourceCodeFetchingProviderMixin
from .proxies import SourceCodeFetchingProxyMixin
from .vyper import SourceCodeFetchingVyperMixin


class SourceCodeFetchingMixin(
    SourceCodeFetchingBaseMixin,
    SourceCodeFetchingVyperMixin,
    SourceCodeFetchingProviderMixin,
    SourceCodeFetchingProxyMixin,
    SourceCodeFetchingExtractionMixin,
):
    """Composite fetching mixin."""

    pass
