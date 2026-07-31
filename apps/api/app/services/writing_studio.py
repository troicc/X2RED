from __future__ import annotations

from app.services.writing_agents import WritingAgentsMixin
from app.services.writing_core import WritingCore
from app.services.writing_flow import WritingFlowMixin


class MultiAgentWritingService(WritingFlowMixin, WritingAgentsMixin, WritingCore):
    """Artifact-driven writing studio with author gates and independent reviewers."""
