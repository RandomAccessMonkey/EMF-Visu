from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import ProjectRow
from ..deps import api_error, get_session
from ..schemas import ErrorBody, ProjectIn, ProjectOut, ProjectSummary

router = APIRouter(prefix="/projects", tags=["projects"])
Db = Annotated[Session, Depends(get_session)]
_ERR: dict[int | str, dict[str, object]] = {404: {"model": ErrorBody}, 503: {"model": ErrorBody}}
OWNER = "local"


def _get(db: Session, project_id: str) -> ProjectRow:
    row = db.get(ProjectRow, project_id)
    if row is None or row.owner_id != OWNER:
        raise api_error(404, "not_found", "unknown project")
    return row


def _out(row: ProjectRow) -> ProjectOut:
    return ProjectOut.model_validate(row, from_attributes=True)


@router.get("", responses=_ERR)
def list_projects(db: Db) -> list[ProjectSummary]:
    rows = db.scalars(select(ProjectRow).where(ProjectRow.owner_id == OWNER)
                      .order_by(ProjectRow.updated_at.desc())).all()
    return [ProjectSummary.model_validate(r, from_attributes=True) for r in rows]


@router.post("", status_code=201, responses=_ERR)
def create_project(body: ProjectIn, db: Db) -> ProjectOut:
    row = ProjectRow(owner_id=OWNER, name=body.name, scene=body.scene.model_dump(mode="json"),
                     view=body.view)
    db.add(row)
    db.commit()
    return _out(row)


@router.get("/{project_id}", responses=_ERR)
def get_project(project_id: str, db: Db) -> ProjectOut:
    return _out(_get(db, project_id))


@router.put("/{project_id}", responses=_ERR)
def update_project(project_id: str, body: ProjectIn, db: Db) -> ProjectOut:
    row = _get(db, project_id)
    row.name, row.scene, row.view = body.name, body.scene.model_dump(mode="json"), body.view
    db.commit()
    return _out(row)


@router.delete("/{project_id}", status_code=204, responses=_ERR)
def delete_project(project_id: str, db: Db) -> Response:
    db.delete(_get(db, project_id))
    db.commit()
    return Response(status_code=204)
