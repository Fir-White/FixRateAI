"""Persistence operations; callers own the transaction and error handling."""
from datetime import date, datetime
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, joinedload
from .models import Mappings


class MaintenanceRepository:
    def __init__(self, session: Session, models: Mappings):
        self.session = session
        self.models = models

    def add(self, table: str, **values):
        """Low-level internal operation; services must validate scope and invariants.

        Never expose table or values directly as an API request.
        """
        obj = self.models[table](**values)
        self.session.add(obj)
        self.session.flush()
        return obj

    def get(self, table: str, identity):
        return self.session.get(self.models[table], identity)

    def equipment_for_site(self, site_id, system_id=None):
        Equipment = self.models["equipment"]
        query = select(Equipment).where(Equipment.site_id == site_id)
        if system_id is not None:
            query = query.where(Equipment.system_id == system_id)
        return self.session.scalars(query.options(joinedload(Equipment.system))).all()

    def ensure_site_system(self, site_id, system_id):
        Site, System = self.models["sites"], self.models["engineering_systems"]
        if self.session.get(Site, site_id) is None:
            raise LookupError("Site not found")
        if self.session.scalar(select(System.system_id).where(
                System.site_id == site_id, System.system_id == system_id)) is None:
            raise LookupError("Engineering system not found for site")

    def retire_equipment(self, site_id, equipment_id):
        Equipment = self.models["equipment"]
        obj = self.session.scalar(select(Equipment).where(Equipment.site_id == site_id,
                                                           Equipment.equipment_id == equipment_id).with_for_update())
        if obj is None:
            raise LookupError("Equipment not found")
        obj.status = "retired"
        self.session.flush()
        return obj

    def rules_for_equipment(self, site_id, equipment_id, as_of: date | None = None):
        Binding, Rule = self.models["rule_equipment"], self.models["maintenance_rules"]
        query = select(Binding).where(Binding.site_id == site_id, Binding.equipment_id == equipment_id)
        if as_of is not None:
            query = query.join(Rule, and_(Binding.site_id == Rule.site_id,
                                         Binding.system_id == Rule.system_id,
                                         Binding.maintenance_rule_id == Rule.maintenance_rule_id)).where(
                Binding.valid_from <= as_of, (Binding.valid_to.is_(None) | (Binding.valid_to >= as_of)),
                Rule.active_from <= as_of, (Rule.active_until.is_(None) | (Rule.active_until >= as_of)),
                Rule.publication_status == "published")
        return self.session.scalars(query.options(joinedload(Binding.rule).joinedload(Rule.operation))).all()

    def orders(self, site_id, *, start: date | None = None, end: date | None = None,
               status: str | None = None, equipment_id=None, user_id=None,
               overdue_at: datetime | None = None):
        Order, Entry = self.models["work_orders"], self.models["schedule_entries"]
        query = select(Order).where(Order.site_id == site_id)
        if start is not None or end is not None:
            query = query.join(Entry, and_(Order.site_id == Entry.site_id,
                                           Order.system_id == Entry.system_id,
                                           Order.schedule_entry_id == Entry.schedule_entry_id,
                                           Order.maintenance_rule_id == Entry.maintenance_rule_id))
            if start is not None:
                query = query.where(Entry.planned_date >= start)
            if end is not None:
                query = query.where(Entry.planned_date <= end)
        if status is not None:
            query = query.where(Order.status == status)
        if equipment_id is not None:
            Link = self.models["work_order_equipment"]
            query = query.where(select(Link.work_order_id).where(Link.site_id == Order.site_id,
                              Link.work_order_id == Order.work_order_id, Link.equipment_id == equipment_id).exists())
        if user_id is not None:
            Assignment = self.models["work_assignments"]
            query = query.where(select(Assignment.work_assignment_id).where(Assignment.site_id == Order.site_id,
                              Assignment.work_order_id == Order.work_order_id, Assignment.user_id == user_id,
                              Assignment.status.not_in(("cancelled", "declined"))).exists())
        if overdue_at is not None:
            if overdue_at.tzinfo is None or overdue_at.utcoffset() is None:
                raise ValueError("overdue_at must be timezone-aware")
            query = query.where(Order.regulatory_deadline_at < overdue_at,
                                Order.status.not_in(("completed", "cancelled")))
        return self.session.scalars(query.options(joinedload(Order.rule), joinedload(Order.entry))).all()

    def history(self, site_id, work_order_id):
        """Return reports and their evidence/reviews in three bounded queries."""
        Report, Evidence, Review = (self.models[t] for t in ("work_reports", "evidence_files", "acceptance_reviews"))
        reports = self.session.scalars(select(Report).where(Report.site_id == site_id, Report.work_order_id == work_order_id).order_by(Report.revision_no)).all()
        evidence = self.session.scalars(select(Evidence).where(Evidence.site_id == site_id, Evidence.work_order_id == work_order_id)).all()
        reviews = self.session.scalars(select(Review).where(Review.site_id == site_id, Review.work_order_id == work_order_id)).all()
        return reports, evidence, reviews

    def forecasts(self, site_id, rule_id):
        Forecast = self.models["forecast_runs"]
        return self.session.scalars(select(Forecast).where(Forecast.site_id == site_id,
                                    Forecast.maintenance_rule_id == rule_id).options(joinedload(Forecast.predictor))
                                    .order_by(Forecast.produced_at)).all()

    def supersede_future_entry(self, site_id, entry_id, today: date):
        Entry, Order = self.models["schedule_entries"], self.models["work_orders"]
        entry = self.session.scalar(select(Entry).where(Entry.site_id == site_id,
                                    Entry.schedule_entry_id == entry_id).with_for_update())
        if entry is None:
            raise LookupError("Schedule entry not found")
        if entry.planned_date <= today or entry.status != "planned":
            raise ValueError("Only future planned entries can be superseded")
        # Avoid changing any entry with an order: the order may have execution history.
        if self.session.scalar(select(Order.work_order_id).where(Order.site_id == site_id,
                               Order.schedule_entry_id == entry_id).limit(1)) is not None:
            raise ValueError("Entry has a work order and cannot be superseded here")
        entry.status = "superseded"
        self.session.flush()
        return entry
