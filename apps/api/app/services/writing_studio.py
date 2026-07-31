from __future__ import annotations

from app.services.author_gates import AuthorGateMixin
from app.services.style_training import StyleTrainingMixin
from app.services.writing_agents import WritingAgentsMixin
from app.services.writing_core import WritingCore
from app.services.writing_durable import DurableAgentRunnerMixin
from app.services.writing_flow import WritingFlowMixin


class MultiAgentWritingService(
    WritingFlowMixin,
    DurableAgentRunnerMixin,
    WritingAgentsMixin,
    StyleTrainingMixin,
    AuthorGateMixin,
    WritingCore,
):
    """Artifact-driven writing studio with author gates and independent reviewers."""
