from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from . import database, learning, models, review_media, schemas
from .serializers import serializar_deteccion


router = APIRouter()


def _get_detection_or_404(detection_id: int, db: Session) -> models.Detection:
    detection = (
        db.query(models.Detection)
        .filter(models.Detection.id == detection_id)
        .first()
    )
    if detection is None:
        raise HTTPException(status_code=404, detail="Detection not found")
    return detection


def _validate_audio_timing(detection: schemas.DetectionCreate) -> None:
    start = detection.audio_start_seconds
    end = detection.audio_end_seconds

    if (start is None) != (end is None):
        raise HTTPException(
            status_code=422,
            detail="audio_start_seconds and audio_end_seconds must be provided together",
        )

    if start is not None and end is not None and end <= start:
        raise HTTPException(
            status_code=422,
            detail="audio_end_seconds must be greater than audio_start_seconds",
        )


@router.post("/detections/", response_model=schemas.DetectionResponse)
def create_detection(
    detection: schemas.DetectionCreate,
    db: Session = Depends(database.get_db),
):
    _validate_audio_timing(detection)

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
        timing_updated = False
        if (
            existing_detection.audio_start_seconds is None
            and detection.audio_start_seconds is not None
        ):
            existing_detection.audio_start_seconds = detection.audio_start_seconds
            timing_updated = True
        if (
            existing_detection.audio_end_seconds is None
            and detection.audio_end_seconds is not None
        ):
            existing_detection.audio_end_seconds = detection.audio_end_seconds
            timing_updated = True

        if timing_updated:
            db.commit()
            db.refresh(existing_detection)

        return serializar_deteccion(existing_detection, db)

    new_detection = models.Detection(
        species=detection.species,
        confidence=detection.confidence,
        timestamp=detection.timestamp,
        filename=detection.filename,
        device_id=db_device.id,
        amplitude=detection.amplitude,
        audio_start_seconds=detection.audio_start_seconds,
        audio_end_seconds=detection.audio_end_seconds,
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


@router.get(
    "/detections/{detection_id}/review-media",
    response_model=schemas.DetectionReviewMediaResponse,
)
def get_detection_review_media(
    detection_id: int,
    db: Session = Depends(database.get_db),
):
    detection = _get_detection_or_404(detection_id, db)

    try:
        audio_path = review_media.resolve_audio_path(detection.filename)
        duration = review_media.get_audio_duration(audio_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    window = review_media.build_review_window(
        duration,
        detection.audio_start_seconds,
        detection.audio_end_seconds,
    )

    return {
        "audio_url": f"/records/{quote(audio_path.name)}",
        "spectrogram_url": f"/detections/{detection_id}/review-spectrogram",
        "audio_duration_seconds": window.audio_duration_seconds,
        "review_start_seconds": window.review_start_seconds,
        "review_end_seconds": window.review_end_seconds,
        "review_duration_seconds": window.review_duration_seconds,
        "audio_start_seconds": window.audio_start_seconds,
        "audio_end_seconds": window.audio_end_seconds,
        "timing_available": window.timing_available,
    }


@router.get("/detections/{detection_id}/review-spectrogram")
def get_detection_review_spectrogram(
    detection_id: int,
    db: Session = Depends(database.get_db),
):
    detection = _get_detection_or_404(detection_id, db)

    try:
        audio_path = review_media.resolve_audio_path(detection.filename)
        duration = review_media.get_audio_duration(audio_path)
        window = review_media.build_review_window(
            duration,
            detection.audio_start_seconds,
            detection.audio_end_seconds,
        )
        image_path = review_media.get_review_spectrogram_path(
            detection.id,
            audio_path,
            window,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(
        image_path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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