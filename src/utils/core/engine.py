"""Public analyzer engine composed from focused mixins."""

from .base import AnalyzerBase
from .descriptor import AnalyzerDescriptorMixin
from .detection import AnalyzerDetectionMixin
from .pipeline import AnalyzerPipelineMixin


class ERC7730Analyzer(
    AnalyzerBase,
    AnalyzerDetectionMixin,
    AnalyzerDescriptorMixin,
    AnalyzerPipelineMixin,
):
    """Analyzer engine with modular flow-oriented implementation."""

    pass
