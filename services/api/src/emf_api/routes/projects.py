from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from emf_core.ampere import AmperePath
from emf_core.circuits import EddyDisk, PassiveCircuit
from emf_core.geometry.surfaces import GaussSurface
from emf_core.induction import FluxSurface
from emf_core.lorentz import TestCharge
from emf_core.scene.models import Scene

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


SURFACES_KEY = "gauss_surfaces"
PATHS_KEY = "ampere_paths"
FLUX_KEY = "flux_surfaces"
CHARGE_KEY = "test_charge"
CIRCUITS_KEY = "circuits"
DISKS_KEY = "eddy_disks"


def _out(row: ProjectRow) -> ProjectOut:
    view = dict(row.view or {})
    surfaces = view.pop(SURFACES_KEY, [])
    paths = view.pop(PATHS_KEY, [])
    flux = view.pop(FLUX_KEY, [])
    charge = view.pop(CHARGE_KEY, None)
    circuits = view.pop(CIRCUITS_KEY, [])
    disks = view.pop(DISKS_KEY, [])
    return ProjectOut(id=row.id, name=row.name, created_at=row.created_at,
                      updated_at=row.updated_at, scene=Scene.model_validate(row.scene), view=view,
                      surfaces=[GaussSurface.model_validate(s) for s in surfaces],
                      paths=[AmperePath.model_validate(p) for p in paths],
                      flux_surfaces=[FluxSurface.model_validate(f) for f in flux],
                      test_charge=TestCharge.model_validate(charge) if charge else None,
                      circuits=[PassiveCircuit.model_validate(c) for c in circuits],
                      eddy_disks=[EddyDisk.model_validate(d) for d in disks])


def _view(body: ProjectIn) -> dict[str, object]:
    return {**body.view, SURFACES_KEY: [s.model_dump(mode="json") for s in body.surfaces],
            PATHS_KEY: [p.model_dump(mode="json") for p in body.paths],
            FLUX_KEY: [f.model_dump(mode="json") for f in body.flux_surfaces],
            **({CHARGE_KEY: body.test_charge.model_dump(mode="json")}
               if body.test_charge is not None else {}),
            **({CIRCUITS_KEY: [c.model_dump(mode="json") for c in body.circuits]}
               if body.circuits else {}),
            **({DISKS_KEY: [d.model_dump(mode="json") for d in body.eddy_disks]}
               if body.eddy_disks else {})}


@router.get("", responses=_ERR)
def list_projects(db: Db) -> list[ProjectSummary]:
    rows = db.scalars(select(ProjectRow).where(ProjectRow.owner_id == OWNER)
                      .order_by(ProjectRow.updated_at.desc())).all()
    return [ProjectSummary.model_validate(r, from_attributes=True) for r in rows]


@router.post("", status_code=201, responses=_ERR)
def create_project(body: ProjectIn, db: Db) -> ProjectOut:
    row = ProjectRow(owner_id=OWNER, name=body.name, scene=body.scene.model_dump(mode="json"),
                     view=_view(body))
    db.add(row)
    db.commit()
    return _out(row)


@router.get("/{project_id}", responses=_ERR)
def get_project(project_id: str, db: Db) -> ProjectOut:
    return _out(_get(db, project_id))


@router.put("/{project_id}", responses=_ERR)
def update_project(project_id: str, body: ProjectIn, db: Db) -> ProjectOut:
    row = _get(db, project_id)
    row.name, row.scene, row.view = body.name, body.scene.model_dump(mode="json"), _view(body)
    db.commit()
    return _out(row)


@router.delete("/{project_id}", status_code=204, responses=_ERR)
def delete_project(project_id: str, db: Db) -> Response:
    db.delete(_get(db, project_id))
    db.commit()
    return Response(status_code=204)
