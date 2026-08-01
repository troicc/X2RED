from __future__ import annotations

from fastapi import Request

from app.providers.base import XSourceProvider
from app.services.cards import CardService
from app.services.discovery import DiscoveryService
from app.services.editorial import EditorialService
from app.services.intake import IntakeService
from app.services.jobs import JobEngine
from app.services.platform_studio import PlatformStudioService
from app.services.publisher import PublishService
from app.services.signal_studio import SignalStudioService
from app.services.writing_studio import MultiAgentWritingService


def get_provider(request: Request) -> XSourceProvider:
    return request.app.state.provider


def get_intake_service(request: Request) -> IntakeService:
    return request.app.state.intake_service


def get_discovery_service(request: Request) -> DiscoveryService:
    return request.app.state.discovery_service


def get_editorial_service(request: Request) -> EditorialService:
    return request.app.state.editorial_service


def get_card_service(request: Request) -> CardService:
    return request.app.state.card_service


def get_job_engine(request: Request) -> JobEngine:
    return request.app.state.job_engine


def get_publish_service(request: Request) -> PublishService:
    return request.app.state.publish_service


def get_signal_service(request: Request) -> SignalStudioService:
    return request.app.state.signal_service


def get_writing_service(request: Request) -> MultiAgentWritingService:
    return request.app.state.writing_service


def get_platform_service(request: Request) -> PlatformStudioService:
    return request.app.state.platform_service
