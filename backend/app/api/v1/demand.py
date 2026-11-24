"""API endpoints for monthly material demand.

Provides the FE03 required endpoints:
- GET `/api/v1/demand/monthly` – returns list of demand records.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.demand import get_monthly_demand

router = APIRouter()

@router.get("/demand/monthly", summary="Monthly material demand")
def read_monthly_demand(db: Session = Depends(get_db)):
    demand = get_monthly_demand(db)
    if not demand:
        # Empty result is acceptable but we expose a clear message
        raise HTTPException(status_code=404, detail="No demand data found")
    return demand
