from __future__ import annotations

from app.services.signal_analysis import SignalAnalysisMixin
from app.services.signal_base import SignalBase
from app.services.signal_monitor import SignalMonitorMixin


class SignalStudioService(SignalMonitorMixin, SignalAnalysisMixin, SignalBase):
    """Facade for monitoring, scoring, and tiered content analysis."""
