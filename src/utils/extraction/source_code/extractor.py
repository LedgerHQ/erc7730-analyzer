"""Public source-code extractor composed from focused flow mixins."""

from .dependencies import SourceCodeDependencyMixin
from .fetching import SourceCodeFetchingMixin
from .signatures import SourceCodeSignatureMixin


class SourceCodeExtractor(
    SourceCodeFetchingMixin,
    SourceCodeSignatureMixin,
    SourceCodeDependencyMixin,
):
    """Composite extractor for contract source retrieval and analysis."""

    pass
