from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from . import database, learning, models, schemas
from .serializers import serializar_deteccion


router = APIRouter()


@router.post("/detections/", response_model=schemas.DetectionResponse)
def create_detection(
    detection: schemas.DetectionCreate,
    db: Session = Depends(database.get_db),
):
    db_device = db.query(models.Device).filter(
        models.Device.name == detection.device_name
    ).first()

    if not db_device:
        db_device = models.Device(name=detection.device_name, location="Desconocida")
        db.add(db_device)
        db.commit()
        db.refresh(db_device)

    existing_detection = (
        db.query(models.Detection)
        .filter(
            models.Detection.device_id == db_device.id,
            models.Detection.timestamp == detection.timestamp,
            models.Detection.species == detection.species,
            models.Detection.filename == detection.filename,
        )
        .first()
    )

    if existing_detection:
        return serializar_deteccion(existing_detection, db)

    new_detection = models.Detection(
        species=detection.species,
        confidence=detection.confidence,
        timestamp=detection.timestamp,
        filename=detection.filename,
        device_id=db_device.id,
        amplitude=detection.amplitude,
    )

    db.add(new_detection)
    db.commit()
    db.refresh(new_detection)
    return serializar_deteccion(new_detection, db)


@router.get("/detections/", response_model=list[schemas.DetectionResponse])
def read_detections(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(database.get_db),
):
    detections = (
        db.query(models.Detection)
        .options(joinedload(models.Detection.review))
        .order_by(models.Detection.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [serializar_deteccion(detection, db) for detection in detections]


@router.patch(
    "/detections/{detection_id}/review",
    response_model=schemas.DetectionReviewResponse,
)
def update_detection_review(
    detection_id: int,
    review_data: schemas.DetectionReviewUpdate,
    db: Session = Depends(database.get_db),
):
    detection = (
        db.query(models.Detection)
        .filter(models.Detection.id == detection_id)
        .first()
    )

    if detection is None:
        raise HTTPException(status_code=404, detail="Detection not found")

    if review_data.status == "corrected" and not review_data.corrected_species:
        raise HTTPException(
            status_code=400,
            detail="corrected_species is required when status is corrected",
        )

    review = (
        db.query(models.DetectionReview)
        .filter(models.DetectionReview.detection_id == detection_id)
        .first()
    )

    now = datetime.now(timezone.utc)

    if review is None:
        review = models.DetectionReview(
            detection_id=detection_id,
            status=review_data.status,
            corrected_species=review_data.corrected_species,
            note=review_data.note,
            reviewer=review_data.reviewer,
            reviewed_at=now,
            updated_at=now,
        )
        db.add(review)
    else:
        review.status = review_data.status
        review.corrected_species = review_data.corrected_species
        review.note = review_data.note
        review.reviewer = review_data.reviewer
        review.reviewed_at = now
        review.updated_at = now

    learning.sync_learning_from_review(
        db,
        detection,
        review_data.status,
        review_data.corrected_species,
    )

    db.commit()
    db.refresh(review)

    return review


@router.get(
    "/detections/{detection_id}/review",
    response_model=schemas.DetectionReviewResponse,
)
def get_detection_review(
    detection_id: int,
    db: Session = Depends(database.get_db),
):
    detection = (
        db.query(models.Detection)
        .filter(models.Detection.id == detection_id)
        .first()
    )

    if detection is None:
        raise HTTPException(status_code=404, detail="Detection not found")

    review = (
        db.query(models.DetectionReview)
        .filter(models.DetectionReview.detection_id == detection_id)
        .first()
    )

    if review is None:
        raise HTTPException(status_code=404, detail="Detection review not found")

    return review


@router.get("/species/options")
def get_species_options(db: Session = Depends(database.get_db)):
    species_rows = (
        db.query(models.Detection.species)
        .filter(models.Detection.species.isnot(None))
        .distinct()
        .order_by(models.Detection.species.asc())
        .all()
    )

    return [row[0] for row in species_rows if row[0]]