from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core import database
from ...domain import models, schemas
from . import service as learning


router = APIRouter()


@router.get("/learning/rules", response_model=list[schemas.LearningRuleResponse])
def read_learning_rules(
    active_only: bool = False,
    site_id: int | None = None,
    db: Session = Depends(database.get_db),
):
    query = db.query(models.LearningRule).order_by(
        models.LearningRule.active.desc(),
        models.LearningRule.support_count.desc(),
        models.LearningRule.updated_at.desc(),
    )

    if active_only:
        query = query.filter(models.LearningRule.active.is_(True))
    if site_id is not None:
        query = query.filter(models.LearningRule.site_id == site_id)

    return query.all()


@router.post("/learning/rebuild", response_model=schemas.LearningRebuildResponse)
def rebuild_learning_rules(db: Session = Depends(database.get_db)):
    result = learning.rebuild_learning(db)
    db.commit()
    return result