from fastapi import APIRouter, Depends, Query, Request, Response
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


@router.get("/node/deployments/legacy-context")
def read_legacy_context(
    device_name: str,
    db: Session = Depends(database.get_db),
):
    return service.legacy_event_context(db, device_name)


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


@router.post(
    "/devices/{device_id}/location-commands",
    response_model=schemas.NodeLocationCommandResponse,
)
def create_location_command(
    device_id: int,
    payload: schemas.NodeLocationCommandCreate,
    request: Request,
    db: Session = Depends(database.get_db),
):
    command = service.request_location_command(
        db,
        device_id=device_id,
        payload=payload,
        requested_by=getattr(request.state, "security_username", "admin"),
    )
    return service.location_command_response(command)


@router.get(
    "/devices/{device_id}/location-commands",
    response_model=list[schemas.NodeLocationCommandResponse],
)
def read_location_commands(
    device_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(database.get_db),
):
    return [
        service.location_command_response(command)
        for command in service.list_location_commands(
            db,
            device_id=device_id,
            limit=limit,
        )
    ]


@router.post(
    "/devices/{device_id}/location-commands/{command_id}/cancel",
    response_model=schemas.NodeLocationCommandResponse,
)
def cancel_location_command(
    device_id: int,
    command_id: int,
    db: Session = Depends(database.get_db),
):
    return service.location_command_response(
        service.cancel_location_command(
            db,
            device_id=device_id,
            command_id=command_id,
        )
    )


@router.get("/node/location-command")
def read_pending_location_command(
    device_name: str,
    db: Session = Depends(database.get_db),
):
    command = service.deliver_location_command(
        db,
        device_name=device_name,
    )
    if command is None:
        return Response(status_code=204)
    return service.location_command_response(command)


@router.post(
    "/node/location-command/ack",
    response_model=schemas.NodeLocationCommandResponse,
)
def acknowledge_location_command(
    payload: schemas.NodeLocationCommandAck,
    db: Session = Depends(database.get_db),
):
    return service.location_command_response(
        service.acknowledge_location_command(db, payload)
    )