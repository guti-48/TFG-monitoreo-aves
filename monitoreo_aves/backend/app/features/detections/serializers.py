from sqlalchemy.orm import Session

from ...domain import models
from ..learning import service as learning


def serializar_review(review: models.DetectionReview | None) -> dict | None:
    if review is None:
        return None

    return {
        "id": review.id,
        "detection_id": review.detection_id,
        "status": review.status,
        "corrected_species": review.corrected_species,
        "note": review.note,
        "reviewer": review.reviewer,
        "reviewed_at": review.reviewed_at,
        "updated_at": review.updated_at,
    }


def serializar_deteccion(detection: models.Detection, db: Session) -> dict:
    return {
        "id": detection.id,
        "species": detection.species,
        "confidence": detection.confidence,
        "timestamp": detection.timestamp,
        "filename": detection.filename,
        "device_id": detection.device_id,
        "amplitude": detection.amplitude,
        "audio_start_seconds": detection.audio_start_seconds,
        "audio_end_seconds": detection.audio_end_seconds,
        "review": serializar_review(detection.review),
        "learned_suggestion": learning.find_suggestion(db, detection),
    }