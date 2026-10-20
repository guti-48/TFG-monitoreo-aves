from datetime import datetime, timezone
import json
import os
import socket
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text

from ...domain import models, schemas
from ..learning import service as learning
from .protocol import Record, naive_utc
from .service import ReplicaConflict, export_page, replica_id


class ReviewData(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: schemas.ReviewStatus
    corrected_species: str | None = None
    note: str | None = None
    reviewer: str | None = None

    @model_validator(mode='after')
    def validate_species(self):
        if self.status == 'corrected' and not self.corrected_species:
            raise ValueError('La correccion requiere una especie')
        return self


class ReviewVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    public_id: UUID
    origin_id: UUID
    origin_name: str = Field(min_length=1, max_length=120)
    created_at: AwareDatetime
    parents: list[UUID] = Field(default_factory=list, max_length=1000)
    detection: Record
    review: ReviewData

    @model_validator(mode='after')
    def validate_version(self):
        self.detection.validate_data('detections')
        if self.public_id in self.parents or len(set(self.parents)) != len(self.parents):
            raise ValueError('Antecesores de revision invalidos')
        return self


class ReviewResolution(BaseModel):
    chosen_id: UUID
    expected_heads: list[UUID] = Field(min_length=1, max_length=1000)


class ReviewPage(BaseModel):
    protocol: int = Field(default=1, ge=1, le=1)
    source_id: UUID
    after: int = Field(ge=0)
    records: list[dict] = Field(max_length=100)


def canonical(version):
    return json.dumps(version.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def detection_record(db, detection):
    return export_page(db, 'detections', detection.id - 1, 1).records[0]


def matching_detections(db, record):
    rows = db.scalars(select(models.Detection).join(models.Deployment).where(
        models.Deployment.public_id == str(record.context.public_id),
        models.Detection.filename == record.data['filename'],
        models.Detection.species == record.data['species'],
    )).all()
    timestamp = naive_utc(datetime.fromisoformat(record.data['timestamp']))
    return [row for row in rows if naive_utc(row.timestamp) == timestamp and row.device.name == record.context.device_name]


def versions_for(db, key):
    return [ReviewVersion.model_validate_json(row.content) for row in db.scalars(
        select(models.ReviewEvent).where(models.ReviewEvent.detection_key == key)
    ).all()]


def active_versions(versions):
    by_id = {str(version.public_id): version for version in versions}
    referenced = {str(parent) for version in versions for parent in version.parents}
    children = {identity: [] for identity in by_id}
    pending = {}
    for identity, version in by_id.items():
        parents = [str(parent) for parent in version.parents if str(parent) in by_id]
        pending[identity] = len(parents)
        for parent in parents:
            children[parent].append(identity)
    ready = [identity for identity, count in pending.items() if not count]
    visited = 0
    while ready:
        identity = ready.pop()
        visited += 1
        for child in children[identity]:
            pending[child] -= 1
            if pending[child] == 0:
                ready.append(child)
    if visited != len(by_id):
        raise ReplicaConflict('El historial de revisiones contiene un ciclo')
    return sorted((v for identity, v in by_id.items() if identity not in referenced), key=lambda v: str(v.public_id))


def store_version(db, version):
    identity = str(version.public_id)
    content = canonical(version)
    existing = db.scalar(select(models.ReviewEvent).where(models.ReviewEvent.public_id == identity))
    if existing:
        if existing.content != content:
            raise ReplicaConflict('Una revision existente tiene contenido diferente')
        return False
    for parent in version.parents:
        known = db.scalar(select(models.ReviewEvent).where(models.ReviewEvent.public_id == str(parent)))
        if known is not None and known.detection_key != version.detection.event_id:
            raise ReplicaConflict('El antecedente pertenece a otra deteccion')
    db.add(models.ReviewEvent(public_id=identity, detection_key=version.detection.event_id, content=content))
    db.flush()
    return True


def materialize(db, key):
    heads = active_versions(versions_for(db, key))
    if not heads:
        raise ReplicaConflict('La revision no tiene una version vigente')
    detection_rows = matching_detections(db, heads[0].detection)
    if not detection_rows:
        raise ReplicaConflict('La deteccion de una revision aun no se ha sincronizado')
    conflict = len({json.dumps(v.review.model_dump(), sort_keys=True) for v in heads}) > 1
    chosen = max(heads, key=lambda v: (v.created_at, str(v.public_id)))
    value = (ReviewData(status='doubtful', note='Revisiones en conflicto; pendiente de resolver') if conflict else chosen.review)
    learning_detection_id = min(row.id for row in detection_rows)
    for detection in detection_rows:
        review = db.scalar(select(models.DetectionReview).where(models.DetectionReview.detection_id == detection.id))
        if review is None:
            review = models.DetectionReview(detection_id=detection.id)
            db.add(review)
        for field, content in value.model_dump().items():
            setattr(review, field, content)
        review.reviewed_at = naive_utc(chosen.created_at)
        review.updated_at = naive_utc(chosen.created_at)
        state = db.get(models.ReviewSyncState, detection.id)
        if state is None:
            state = models.ReviewSyncState(detection_id=detection.id, detection_key=key)
            db.add(state)
        state.heads = json.dumps([str(v.public_id) for v in heads])
        state.conflict = conflict
        db.flush()
        learning_status = value.status if detection.id == learning_detection_id else 'unreviewed'
        learning.sync_learning_from_review(db, detection, learning_status, value.corrected_species)
    db.flush()


def begin_write(db):
    identity = replica_id(db)
    db.commit()
    db.execute(text('BEGIN IMMEDIATE'))
    return identity


def new_version(identity, record, review, parents, created_at=None):
    return ReviewVersion(public_id=uuid4(), origin_id=identity,
                         origin_name=os.getenv('BIRDMONITOR_REPLICA_NAME', socket.gethostname())[:120],
                         created_at=created_at or datetime.now(timezone.utc), parents=parents,
                         detection=record, review=review)


def bootstrap_reviews(db, *, reconcile_legacy=False):
    migration = '20261016_review_history_v1'
    if not reconcile_legacy and db.get(models.SchemaMigration, migration) is not None:
        return
    identity = begin_write(db)
    try:
        migrated = db.get(models.SchemaMigration, migration) is not None
        if migrated and not reconcile_legacy:
            db.commit()
            return
        query = select(models.DetectionReview).outerjoin(
            models.ReviewSyncState, models.ReviewSyncState.detection_id == models.DetectionReview.detection_id,
        )
        if not reconcile_legacy:
            query = query.where(models.ReviewSyncState.detection_id.is_(None))
        pending = db.scalars(query).all()
        roots = []
        for review in pending:
            data = ReviewData(**{name: getattr(review, name) for name in ReviewData.model_fields})
            state = db.get(models.ReviewSyncState, review.detection_id)
            parents = []
            if state is not None:
                heads = active_versions(versions_for(db, state.detection_key))
                expected = (ReviewData(status='doubtful', note='Revisiones en conflicto; pendiente de resolver')
                            if state.conflict else max(heads, key=lambda v: (v.created_at, str(v.public_id))).review)
                if data == expected:
                    continue
                parents = json.loads(state.heads)
            record = detection_record(db, review.detection)
            roots.append(new_version(identity, record, data, parents,
                                     naive_utc(review.updated_at or review.reviewed_at).replace(tzinfo=timezone.utc)))
        keys = set()
        for version in roots:
            store_version(db, version)
            keys.add(version.detection.event_id)
        for key in keys:
            materialize(db, key)
        if not migrated:
            db.add(models.SchemaMigration(version=migration, description='Conserva las revisiones anteriores como versiones iniciales'))
        db.commit()
    except BaseException:
        db.rollback()
        raise


def review_state(db, detection):
    state = db.get(models.ReviewSyncState, detection.id)
    if state is None:
        return {'conflict': False, 'heads': [], 'alternatives': []}
    heads = active_versions(versions_for(db, state.detection_key))
    return {'conflict': state.conflict, 'heads': [str(v.public_id) for v in heads],
            'alternatives': [{'public_id': str(v.public_id), 'origin_id': str(v.origin_id),
                              'origin_name': v.origin_name, 'created_at': v.created_at.isoformat(),
                              **v.review.model_dump()} for v in heads]}


def write_review(db, detection, data, *, chosen_id=None, expected_heads=None):
    bootstrap_reviews(db)
    identity = begin_write(db)
    try:
        db.expire_all()
        record = detection_record(db, detection)
        heads = active_versions(versions_for(db, record.event_id))
        state = review_state(db, detection)
        if chosen_id is not None:
            if set(expected_heads or []) != set(state['heads']):
                raise ReplicaConflict('Han llegado nuevas revisiones; vuelve a abrir el conflicto')
            chosen = next((v for v in heads if str(v.public_id) == str(chosen_id)), None)
            if chosen is None:
                raise ReplicaConflict('La revision elegida ya no esta vigente')
            value, parents = chosen.review, state['heads']
        else:
            if state['conflict']:
                raise ReplicaConflict('Resuelve primero el conflicto de revisiones')
            value = ReviewData(**data.model_dump(exclude={'base_versions'}))
            parents = [str(p) for p in data.base_versions] if data.base_versions is not None else state['heads']
            known = {str(v.public_id) for v in versions_for(db, record.event_id)}
            if not set(parents) <= known:
                raise ReplicaConflict('La version revisada no esta disponible; recarga la deteccion')
        version = new_version(identity, record, value, parents)
        store_version(db, version)
        materialize(db, record.event_id)
        db.commit()
        db.expire_all()
        return db.scalar(select(models.DetectionReview).where(models.DetectionReview.detection_id == detection.id))
    except BaseException:
        db.rollback()
        raise


def export_reviews(db, after, limit):
    bootstrap_reviews(db)
    source = replica_id(db)
    rows = db.scalars(select(models.ReviewEvent).where(models.ReviewEvent.id > after).order_by(models.ReviewEvent.id).limit(limit)).all()
    return {'protocol': 1, 'source_id': source, 'after': after,
            'records': [{'sequence': row.id, 'version': json.loads(row.content)} for row in rows]}


def import_reviews(db, page):
    page = ReviewPage.model_validate(page)
    bootstrap_reviews(db)
    identity = begin_write(db)
    source = str(page.source_id)
    try:
        if source == identity:
            raise ReplicaConflict('No se pueden importar revisiones de la propia replica')
        cursor = db.get(models.ReplicaCursor, (source, 'reviews'))
        if page.after != (cursor.position if cursor else 0):
            raise ReplicaConflict('El cursor de revisiones ha cambiado')
        position = page.after
        keys, added = set(), 0
        for record in page.records:
            if set(record) != {'sequence', 'version'} or type(record['sequence']) is not int or record['sequence'] <= position:
                raise ReplicaConflict('Pagina de revisiones fuera de orden')
            version = ReviewVersion.model_validate(record['version'])
            added += store_version(db, version)
            keys.add(version.detection.event_id)
            position = record['sequence']
        for key in keys:
            materialize(db, key)
        if cursor is None:
            cursor = models.ReplicaCursor(source_id=source, kind='reviews')
            db.add(cursor)
        cursor.position, cursor.updated_at = position, datetime.now(timezone.utc)
        db.commit()
        return added
    except BaseException:
        db.rollback()
        raise
