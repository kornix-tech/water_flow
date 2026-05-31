from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import CreateProjectRequest, ProjectInfo

router = APIRouter()


def _default_project(request: Request, name: str = "default") -> ProjectInfo:
    settings = request.app.state.settings
    return ProjectInfo(id="default", name=name, workspace=str(settings.workspace))


@router.get("", response_model=list[ProjectInfo])
def list_projects(request: Request) -> list[ProjectInfo]:
    return [_default_project(request)]


@router.post("", response_model=ProjectInfo)
def create_project(payload: CreateProjectRequest, request: Request) -> ProjectInfo:
    # Web-режим пока использует один workspace; endpoint оставлен как точка расширения.
    return _default_project(request, payload.name)


@router.get("/{project_id}", response_model=ProjectInfo)
def get_project(project_id: str, request: Request) -> ProjectInfo:
    return _default_project(request, project_id)
