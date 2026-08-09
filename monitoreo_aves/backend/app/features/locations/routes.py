from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from ...core import database
from ...domain import models, schemas
from . import service


router = APIRouter()


@router.get("/sites/", response_model=list[schemas.SiteResponse])
def read_sites(
    include_archived: bool = False,
    db: Session = Depends(database.get_db),
):
    query = db.query(models.Site).order_by(models.Site.name.asc())
    if not include_archived:
        query = query.filter(models.Site.archived_at.is_(None))
    return [service.site_response(db, site) for site in query.all()]


@router.get("/sites/{site_id}", response_model=schemas.SiteResponse)
def read_site(site_id: int, db: Session = Depends(database.get_db)):
    return service.site_response(db, service.get_site_or_404(db, site_id))


@router.post("/sites/", response_model=schemas.SiteResponse)
def create_site(
    payload: schemas.SiteCreate,
    db: Session = Depends(database.get_db),
):
    return service.site_response(db, service.create_site(db, payload))


@router.patch("/sites/{site_id}", response_model=schemas.SiteResponse)
def update_site(
    site_id: int,
    payload: schemas.SiteUpdate,
    db: Session = Depends(database.get_db),
):
    site = service.get_site_or_404(db, site_id)
    return service.site_response(db, service.update_site(db, site, payload))


@router.post(
    "/node/deployments/activate",
    response_model=schemas.DeploymentResponse,
)
def activate_deployment(
    payload: schemas.DeploymentActivate,
    db: Session = Depends(database.get_db),
):
    return service.deployment_response(service.activate_deployment(db, payload))


@router.get(
    "/sites/{site_id}/deployments",
    response_model=list[schemas.DeploymentResponse],
)
def read_site_deployments(
    site_id: int,
    db: Session = Depends(database.get_db),
):
    service.get_site_or_404(db, site_id)
    deployments = db.query(models.Deployment).options(
        joinedload(models.Deployment.device),
        joinedload(models.Deployment.site),
    ).filter(models.Deployment.site_id == site_id).order_by(
        models.Deployment.started_at.desc()
    ).all()
    return [service.deployment_response(item) for item in deployments]


@router.get(
    "/devices/{device_id}/deployments",
    response_model=list[schemas.DeploymentResponse],
)
def read_device_deployments(
    device_id: int,
    db: Session = Depends(database.get_db),
):
    deployments = db.query(models.Deployment).options(
        joinedload(models.Deployment.device),
        joinedload(models.Deployment.site),
    ).filter(models.Deployment.device_id == device_id).order_by(
        models.Deployment.started_at.desc()
    ).all()
    return [service.deployment_response(item) for item in deployments]