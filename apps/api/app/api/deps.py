from __future__ import annotations

from fastapi import Request

from app.providers.base import XSourceProvider
from app.services.editorial import EditorialService
from app.services.intake import IntakeService
from app.services.publisher import PublishService


def get_provider(request: Request) -> XSourceProvider:
    return request.app.state.provider


def get_intake_service(request: Request) -> IntakeService:
    return request.app.state.intake_service


def get_editorial_service(request: Request) -> EditorialService:
    return request.app.state.editorial_service


def get_publish_service(request: Request) -> PublishService:
    return request.app.state.publish_service
