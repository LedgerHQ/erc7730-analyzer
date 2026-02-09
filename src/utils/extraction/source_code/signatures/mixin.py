"""Composed signature mixin from smaller signature helpers."""

from .lookup import SourceCodeSignatureLookupMixin
from .selector import SourceCodeSignatureSelectorMixin
from .types import SourceCodeSignatureTypeMixin


class SourceCodeSignatureMixin(
    SourceCodeSignatureTypeMixin,
    SourceCodeSignatureLookupMixin,
    SourceCodeSignatureSelectorMixin,
):
    """Composite signature mixin."""

    pass
