"""API endpoints for monthly material demand.

Provides the FE03 required endpoints:
- GET `/api/v1/demand/monthly` – returns list of demand records.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.demand import get_monthly_demand

router = APIRouter()

from pydantic import BaseModel

class DemandRecord(BaseModel):
    material_id: str
    quantity: float
    unit: str
    month: int
    work_id: str
    equipment_id: str | None = None
    basis: str | None = None

@router.get("/demand/monthly", summary="Monthly material demand", response_model=list[DemandRecord])
def read_monthly_demand(db: Session = Depends(get_db)):
    demand = get_monthly_demand(db)
    if not demand:
        # Empty result is acceptable but we expose a clear message
        raise HTTPException(status_code=404, detail="No demand data found")
    return demand
