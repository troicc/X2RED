from __future__ import annotations

from fastapi import Request

from app.providers.base import XSourceProvider
from app.services.cards import CardService
from app.services.editorial import EditorialService
from app.services.intake import IntakeService
from app.services.jobs import JobEngine
from app.services.publisher import PublishService


def get_provider(request: Request) -> XSourceProvider:
    return request.app.state.provider


def get_intake_service(request: Request) -> IntakeService:
    return request.app.state.intake_service


def get_editorial_service(request: Request) -> EditorialService:
    return request.app.state.editorial_service


def get_card_service(request: Request) -> CardService:
    return request.app.state.card_service


def get_job_engine(request: Request) -> JobEngine:
    return request.app.state.job_engine


def get_publish_service(request: Request) -> PublishService:
    return request.app.state.publish_service
