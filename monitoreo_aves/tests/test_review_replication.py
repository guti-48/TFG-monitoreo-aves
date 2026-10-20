from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from backend.app.domain import models, schemas
from backend.app.features.replication.service import export_page, import_page, replica_id, ReplicaConflict
from backend.app.features.replication import reviews
from test_replication import stores, add_capture


def mirror(source, target):
    with source() as db:
        page = export_page(db, 'detections', 0, 100)
    with target() as db:
        import_page(db, page)


def exchange(source, target):
    with source() as db:
        identity = replica_id(db)
    with target() as db:
        cursor = db.get(models.ReplicaCursor, (identity, 'reviews'))
        after = cursor.position if cursor else 0
    with source() as db:
        page = reviews.export_reviews(db, after, 100)
    with target() as db:
        return reviews.import_reviews(db, page)


def update(store, status, parents=None, note=None):
    with store() as db:
        detection = db.query(models.Detection).first()
        value = schemas.DetectionReviewUpdate(status=status, base_versions=parents, note=note)
        reviews.write_review(db, detection, value)
        return reviews.review_state(db, detection)


def state(store):
    with store() as db:
        detection = db.query(models.Detection).first()
        return reviews.review_state(db, detection), detection.review.status


def test_offline_changes_conflict_and_resolution_converges_without_deleting_history(stores):
    a,b,c = stores
    add_capture(a)
    mirror(a,b)
    mirror(a,c)
    first = update(a, 'validated', [], 'Comprobada en Mac')
    second = update(b, 'noise', [], 'Ruido en Windows')
    assert exchange(a,b) == 1
    assert exchange(b,a) == 1
    for store in (a,b):
        value, status = state(store)
        assert value['conflict'] is True
        assert status == 'doubtful'
        assert len(value['alternatives']) == 2
        with store() as db:
            assert db.query(models.LearningExample).count() == 0
        with pytest.raises(ReplicaConflict, match='Resuelve primero'):
            update(store, 'validated')
    with a() as db:
        detection = db.query(models.Detection).first()
        value = reviews.review_state(db, detection)
        reviews.write_review(db, detection, None, chosen_id=first['heads'][0], expected_heads=value['heads'])
    exchange(a,b)
    exchange(b,c)
    for store in (a,b,c):
        value,status = state(store)
        assert not value['conflict']
        assert status == 'validated'
        with store() as db:
            assert db.query(models.ReviewEvent).count() == 3
    assert exchange(b,a) == 0
    assert exchange(a,b) == 0


def test_causally_later_edit_and_identical_concurrent_edits_do_not_conflict(stores):
    a,b,_ = stores
    add_capture(a);mirror(a,b)
    initial=update(a,'validated',[])
    exchange(a,b)
    update(b,'noise',initial['heads'])
    exchange(b,a)
    assert state(a)[1]=='noise'
    assert state(a)[0]['conflict'] is False
    current=state(a)[0]['heads']
    update(a,'discarded',current)
    update(b,'discarded',current)
    exchange(a,b);exchange(b,a)
    assert state(a)[0]['conflict'] is False
    assert len(state(a)[0]['heads'])==2


def test_stale_browser_edit_preserves_both_and_stale_resolution_is_rejected(stores):
    a,_,_=stores
    add_capture(a)
    initial=update(a,'validated',[])
    update(a,'noise',initial['heads'])
    update(a,'discarded',initial['heads'])
    assert state(a)[0]['conflict'] is True
    with a() as db:
        detection=db.query(models.Detection).first()
        heads=reviews.review_state(db,detection)['heads']
        with pytest.raises(ReplicaConflict,match='nuevas revisiones'):
            reviews.write_review(db,detection,None,chosen_id=heads[0],expected_heads=heads[:1])
        assert db.query(models.ReviewEvent).count()==3


def test_legacy_reviews_are_migrated_once_and_keep_conflicting_notes(stores):
    a,b,_=stores
    add_capture(a);mirror(a,b)
    for store,note in [(a,'Nota Mac'),(b,'Nota Windows')]:
        with store() as db:
            detection=db.query(models.Detection).first()
            db.add(models.DetectionReview(detection_id=detection.id,status='validated',note=note,
                                          reviewer='persona',reviewed_at=datetime(2026,1,1),updated_at=datetime(2026,1,1)))
            db.commit()
            reviews.bootstrap_reviews(db);reviews.bootstrap_reviews(db)
            assert db.query(models.ReviewEvent).count()==1
    exchange(a,b)
    assert {v['note'] for v in state(b)[0]['alternatives']}=={'Nota Mac','Nota Windows'}


def test_missing_detection_does_not_advance_cursor_and_retry_succeeds(stores):
    a,b,_=stores
    add_capture(a);update(a,'validated',[])
    with pytest.raises(ReplicaConflict,match='aun no se ha sincronizado'):
        exchange(a,b)
    with b() as db:
        assert db.query(models.ReviewEvent).count()==0
        assert db.query(models.ReplicaCursor).filter_by(kind='reviews').count()==0
    mirror(a,b)
    assert exchange(a,b)==1


def test_legacy_duplicate_detections_contribute_one_learning_example(stores):
    a,b,_=stores
    add_capture(a)
    with a() as db:
        original = db.query(models.Detection).one()
        db.execute(text("UPDATE detections SET timestamp = '2026-10-01 12:00:00'"))
        db.add(models.Detection(**{column.name: getattr(original, column.name)
                                  for column in models.Detection.__table__.columns if column.name != 'id'}))
        db.commit()
    mirror(a,b)
    update(a,'validated',[])
    exchange(a,b)
    for store in (a,b):
        with store() as db:
            assert all(row.review.status == 'validated' for row in db.query(models.Detection))
            assert db.query(models.LearningExample).count() == 1
            assert db.query(models.LearningRule).one().support_count == 1
    update(a,'noise')
    exchange(a,b)
    for store in (a,b):
        with store() as db:
            assert db.query(models.LearningExample).count() == 1
            assert db.query(models.LearningExample).one().learned_status == 'noise'


def test_changed_duplicate_version_is_rejected_atomically(stores):
    a,b,_=stores
    add_capture(a);mirror(a,b);update(a,'validated',[])
    exchange(a,b)
    with a() as db: page=reviews.export_reviews(db,0,100)
    page['after']=1
    page['records'][0]['sequence']=2
    page['records'][0]['version']['review']['status']='discarded'
    with b() as db:
        with pytest.raises(ReplicaConflict,match='contenido diferente'):
            reviews.import_reviews(db,page)
        assert db.query(models.ReviewEvent).count()==1
        assert db.query(models.ReplicaCursor).filter_by(kind='reviews').one().position==1


def test_dashboard_api_exposes_conflict_and_requires_current_versions_to_resolve(client):
    name = 'review-sync-api-' + uuid4().hex
    response = client.post('/detections/', json={'species': 'Passer domesticus', 'confidence': .9,
        'timestamp': '2026-06-01T08:55:00+00:00', 'filename': name + '.wav', 'device_name': name, 'amplitude': .1})
    assert response.status_code == 200
    detection = response.json()
    url=f"/detections/{detection['id']}"
    assert client.patch(url+'/review',json={'status':'validated','base_versions':[]}).status_code==200
    assert client.patch(url+'/review',json={'status':'noise','base_versions':[]}).status_code==200
    current=client.get(url+'/review-sync').json()
    assert current['conflict']
    rows=client.get('/detections/').json()
    assert next(row for row in rows if row['id']==detection['id'])['review_sync']['conflict']
    chosen=next(v for v in current['alternatives'] if v['status']=='validated')
    assert client.post(url+'/review-resolve',json={'chosen_id':chosen['public_id'],'expected_heads':current['heads'][:1]}).status_code==409
    response=client.post(url+'/review-resolve',json={'chosen_id':chosen['public_id'],'expected_heads':current['heads']})
    assert response.status_code==200
    assert response.json()['status']=='validated'
    assert client.get(url+'/review-sync').json()['conflict'] is False


def test_restart_recovers_edits_made_after_rollback_to_legacy_code(stores):
    a,b,_ = stores
    add_capture(a);mirror(a,b)
    first = update(a, 'validated', [], 'Antes de restaurar')
    exchange(a,b)
    with a() as db:
        review = db.query(models.DetectionReview).one()
        review.status = 'noise'
        review.note = 'Edicion con la version antigua'
        review.updated_at = datetime(2026,10,20)
        db.commit()
        reviews.bootstrap_reviews(db, reconcile_legacy=True)
        reviews.bootstrap_reviews(db, reconcile_legacy=True)
        assert db.query(models.ReviewEvent).count() == 2
        latest = reviews.active_versions(reviews.versions_for(db, db.query(models.ReviewSyncState).one().detection_key))[0]
        assert [str(parent) for parent in latest.parents] == first['heads']
    exchange(a,b)
    assert state(b)[1] == 'noise'
    assert state(b)[0]['alternatives'][0]['note'] == 'Edicion con la version antigua'
