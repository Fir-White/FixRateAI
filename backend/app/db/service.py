"""Site-scoped entry point for explicitly supported creation operations."""
from uuid import UUID
from .dto import equipment_create_values
from .repository import MaintenanceRepository
from .session import service_transaction
from app.schemas.maintenance_api import EquipmentCreate


class MaintenanceService:
    def __init__(self, repository: MaintenanceRepository, site_id: UUID):
        self.repository = repository
        self.site_id = site_id

    def create_equipment(self, request: EquipmentCreate, *, system_id: UUID):
        if request.site_id != self.site_id:
            raise ValueError("request site does not match the authorised site")
        values = equipment_create_values(request, system_id=system_id)
        with service_transaction(self.repository.session):
            self.repository.ensure_site_system(self.site_id, system_id)
            equipment = self.repository.add("equipment", **values)
        return equipment
