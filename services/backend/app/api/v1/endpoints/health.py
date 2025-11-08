from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/", summary="Check API and database health.")
def get_health_status(db: Session = Depends(get_db)) -> dict[str, str]:
    """Simple health-check endpoint that also pings the database."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
