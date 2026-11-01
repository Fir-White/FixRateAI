"""Domain Guardrails for operations that cannot be visually verified by photos."""
from __future__ import annotations

from uuid import UUID
from ml_service.app.schemas import ChecklistItem, ItemPhotoReview


class VisualGuardrailPolicy:
    """Enforces domain rules for hidden, metrological, or non-verifiable checklist items."""

    HIDDEN_OPERATIONS_EXPLANATION = (
        "Операция скрытого характера или метрологический контроль: "
        "факт выполнения подтверждается приборным журналом/показаниями, а не фотофиксацией."
    )

    @classmethod
    def is_item_verifiable(cls, item: ChecklistItem) -> bool:
        """Return True if item can be verified visually, False if hidden."""
        return item.visual_verifiability != "not_verifiable"

    @classmethod
    def create_not_verifiable_review(
        cls,
        checklist_item_id: UUID,
        before_photo_id: UUID | None = None,
        after_photo_id: UUID | None = None,
        custom_note: str | None = None,
    ) -> ItemPhotoReview:
        """Create a standard ItemPhotoReview with verdict='not_verifiable'."""
        return ItemPhotoReview(
            checklist_item_id=checklist_item_id,
            verdict="not_verifiable",
            before_photo_id=before_photo_id,
            after_photo_id=after_photo_id,
            observation=custom_note or cls.HIDDEN_OPERATIONS_EXPLANATION,
            scores=[],
        )
