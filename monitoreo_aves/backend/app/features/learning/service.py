from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from ...domain import models
MIN_SUPPORT_TO_SUGGEST = 3
MIN_SUPPORT_TO_AUTO_APPLY = 5
CONFIDENCE_TOLERANCE = 0.05
AMPLITUDE_TOLERANCE = 0.03
LEARNABLE_STATUSES = {"validated", "corrected", "noise", "discarded"}

def normalize_corrected_species(status: str, corrected_species: Optional[str]) -> Optional[str]:
    if status == "noise":
        return "Noise_Ruido Ambiente"
    if status == "discarded":
        return None

    cleaned = corrected_species.strip() if corrected_species else None
    return cleaned or None

def effective_species(original_species: str, status: str, corrected_species: Optional[str]) -> Optional[str]:
    if status == "corrected" and corrected_species:
        return corrected_species
    if status == "noise":
        return corrected_species or "Noise_Ruido Ambiente"
    if status == "discarded":
        return None
    return original_species

def learning_confidence(support_count: int) -> float:
    return round(min(0.95, 0.50 + (support_count * 0.10)), 2)

def _find_rule(
    db: Session,
    device_id: int,
    original_species: str,
    learned_status: str,
    corrected_species: Optional[str],
) -> Optional[models.LearningRule]:
    query = (
        db.query(models.LearningRule)
        .filter(
            models.LearningRule.device_id == device_id,
            models.LearningRule.original_species == original_species,
            models.LearningRule.learned_status == learned_status,
        )
    )

    if corrected_species is None:
        query = query.filter(models.LearningRule.corrected_species.is_(None))
    else:
        query = query.filter(models.LearningRule.corrected_species == corrected_species)

    return query.first()

def _get_or_create_rule(
    db: Session,
    detection: models.Detection,
    learned_status: str,
    corrected_species: Optional[str],
) -> models.LearningRule:
    rule = _find_rule(
        db,
        detection.device_id,
        detection.species,
        learned_status,
        corrected_species,
    )

    if rule is not None:
        return rule

    now = datetime.now(timezone.utc)
    rule = models.LearningRule(
        device_id=detection.device_id,
        original_species=detection.species,
        learned_status=learned_status,
        corrected_species=corrected_species,
        min_confidence=detection.confidence,
        max_confidence=detection.confidence,
        min_amplitude=detection.amplitude,
        max_amplitude=detection.amplitude,
        support_count=0,
        active=False,
        auto_apply=False,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.flush()
    return rule

def recompute_rule(db: Session, rule: models.LearningRule) -> None:
    examples = (
        db.query(models.LearningExample)
        .filter(models.LearningExample.rule_id == rule.id)
        .all()
    )

    now = datetime.now(timezone.utc)
    support_count = len(examples)
    rule.support_count = support_count
    rule.active = support_count >= MIN_SUPPORT_TO_SUGGEST
    rule.auto_apply = (
        support_count >= MIN_SUPPORT_TO_AUTO_APPLY
        and rule.learned_status in {"corrected", "noise", "discarded"}
    )
    rule.updated_at = now

    if not examples:
        return

    confidences = [example.confidence for example in examples]
    amplitudes = [
        example.amplitude
        for example in examples
        if example.amplitude is not None
    ]

    rule.min_confidence = min(confidences)
    rule.max_confidence = max(confidences)
    rule.min_amplitude = min(amplitudes) if amplitudes else None
    rule.max_amplitude = max(amplitudes) if amplitudes else None

def sync_learning_from_review(
    db: Session,
    detection: models.Detection,
    status: str,
    corrected_species: Optional[str],
) -> Optional[models.LearningRule]:
    existing_example = (
        db.query(models.LearningExample)
        .filter(models.LearningExample.detection_id == detection.id)
        .first()
    )
    previous_rule = existing_example.rule if existing_example else None

    if status not in LEARNABLE_STATUSES:
        if existing_example is not None:
            db.delete(existing_example)
            db.flush()
            if previous_rule is not None:
                recompute_rule(db, previous_rule)
        return None

    normalized_species = normalize_corrected_species(status, corrected_species)
    rule = _get_or_create_rule(db, detection, status, normalized_species)

    if existing_example is None:
        existing_example = models.LearningExample(
            detection_id=detection.id,
            rule_id=rule.id,
            device_id=detection.device_id,
            original_species=detection.species,
            learned_status=status,
            corrected_species=normalized_species,
            confidence=detection.confidence,
            amplitude=detection.amplitude,
        )
        db.add(existing_example)
    else:
        existing_example.rule_id = rule.id
        existing_example.device_id = detection.device_id
        existing_example.original_species = detection.species
        existing_example.learned_status = status
        existing_example.corrected_species = normalized_species
        existing_example.confidence = detection.confidence
        existing_example.amplitude = detection.amplitude
        existing_example.updated_at = datetime.now(timezone.utc)

    db.flush()

    if previous_rule is not None and previous_rule.id != rule.id:
        recompute_rule(db, previous_rule)

    recompute_rule(db, rule)
    return rule

def find_suggestion(db: Session, detection: models.Detection) -> Optional[dict]:
    if detection.review is not None and detection.review.status != "unreviewed":
        return None

    confidence_min = detection.confidence - CONFIDENCE_TOLERANCE
    confidence_max = detection.confidence + CONFIDENCE_TOLERANCE

    query = (
        db.query(models.LearningRule)
        .filter(
            models.LearningRule.device_id == detection.device_id,
            models.LearningRule.original_species == detection.species,
            models.LearningRule.active.is_(True),
            models.LearningRule.min_confidence <= confidence_max,
            models.LearningRule.max_confidence >= confidence_min,
        )
    )

    if detection.amplitude is not None:
        amplitude_min = detection.amplitude - AMPLITUDE_TOLERANCE
        amplitude_max = detection.amplitude + AMPLITUDE_TOLERANCE
        query = query.filter(
            or_(
                models.LearningRule.min_amplitude.is_(None),
                models.LearningRule.max_amplitude.is_(None),
                and_(
                    models.LearningRule.min_amplitude <= amplitude_max,
                    models.LearningRule.max_amplitude >= amplitude_min,
                ),
            )
        )

    rule = (
        query.order_by(
            models.LearningRule.auto_apply.desc(),
            models.LearningRule.support_count.desc(),
            models.LearningRule.updated_at.desc(),
        )
        .first()
    )

    if rule is None:
        return None

    learned_species = effective_species(
        detection.species,
        rule.learned_status,
        rule.corrected_species,
    )
    return {
        "rule_id": rule.id,
        "status": rule.learned_status,
        "corrected_species": rule.corrected_species,
        "effective_species": learned_species,
        "learning_confidence": learning_confidence(rule.support_count),
        "support_count": rule.support_count,
        "auto_apply": rule.auto_apply,
        "reason": (
            f"{rule.support_count} revisiones humanas previas coinciden "
            f"para {rule.original_species}"
        ),
    }

def rebuild_learning(db: Session) -> dict:
    db.query(models.LearningExample).delete()
    db.query(models.LearningRule).delete()
    db.flush()

    reviews = (
        db.query(models.DetectionReview)
        .join(models.Detection)
        .order_by(models.DetectionReview.reviewed_at.asc())
        .all()
    )

    for review in reviews:
        sync_learning_from_review(
            db,
            review.detection,
            review.status,
            review.corrected_species,
        )

    db.flush()
    return {
        "rules": db.query(models.LearningRule).count(),
        "examples": db.query(models.LearningExample).count(),
    }
