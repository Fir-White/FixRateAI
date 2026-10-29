"""CLIP Zero-Shot classifier for before/after maintenance photo comparison."""
from __future__ import annotations

import io
from typing import Literal
from uuid import UUID
import numpy as np
from PIL import Image

from ml_service.app.core.config import settings
from ml_service.app.schemas import ImageLabelScore, ItemPhotoReview

DEFAULT_PROMPTS = [
    "a dirty, dusty, clogged industrial equipment surface",
    "a clean, serviced, shiny industrial equipment surface",
]
CLEAN_LABEL = "a clean equipment surface"


class CLIPZeroShotClassifier:
    """Classifies visible changes between before/after photos using CLIP Zero-Shot reasoning."""

    def __init__(
        self,
        model_name: str = settings.clip_model_name,
        delta_threshold: float = settings.clip_delta_threshold,
        prompt_set_version: str = settings.prompt_set_version,
    ):
        self.model_name = model_name
        self.delta_threshold = delta_threshold
        self.prompt_set_version = prompt_set_version
        self._processor = None
        self._model = None
        self._is_torch_available = False
        self._init_backend()

    def _init_backend(self) -> None:
        """Attempt to load transformers and torch if available."""
        try:
            import torch
            from transformers import AutoProcessor, CLIPModel
            self._processor = AutoProcessor.from_pretrained(self.model_name)
            self._model = CLIPModel.from_pretrained(self.model_name)
            self._model.eval()
            self._is_torch_available = True
        except Exception:
            # Fall back to offline deterministic evaluation if transformers/torch or weights missing
            self._is_torch_available = False

    @property
    def is_torch_active(self) -> bool:
        return self._is_torch_available and self._model is not None

    def _infer_single_image(self, image_bytes: bytes) -> float:
        """Infer probability of cleanliness for a single image in range [0.0, 1.0]."""
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            img = pil_img.convert("RGB")

            if self.is_torch_active:
                import torch
                inputs = self._processor(
                    text=DEFAULT_PROMPTS,
                    images=img,
                    return_tensors="pt",
                    padding=True,
                )
                with torch.no_grad():
                    outputs = self._model(**inputs)
                    logits_per_image = outputs.logits_per_image
                    probs = logits_per_image.softmax(dim=1).cpu().numpy()[0]
                    # Index 1 corresponds to clean label
                    return float(probs[1])
            else:
                # Deterministic visual heuristic (used for hermetic tests and offline fallback)
                # Evaluates brightness and normalized high-frequency edge density
                gray = img.convert("L")
                arr = np.array(gray, dtype=np.float64)
                mean_b = float(np.mean(arr)) / 255.0
                grad_y = np.abs(np.diff(arr, axis=0))
                grad_x = np.abs(np.diff(arr, axis=1))
                edge_intensity = (float(np.mean(grad_y)) + float(np.mean(grad_x))) / 50.0

                # Cleaner surfaces typically show higher reflective brightness and cleaner uniform contrast
                score = 0.5 * mean_b + 0.5 * min(1.0, edge_intensity)
                return float(np.clip(score, 0.05, 0.95))

    def evaluate_pair(
        self,
        checklist_item_id: UUID,
        before_photo_id: UUID,
        after_photo_id: UUID,
        before_bytes: bytes,
        after_bytes: bytes,
    ) -> ItemPhotoReview:
        """Evaluate a pair of before/after photos and return structured item review."""
        p_before = self._infer_single_image(before_bytes)
        p_after = self._infer_single_image(after_bytes)

        delta = p_after - p_before

        if delta >= self.delta_threshold:
            verdict: Literal["visible_change", "no_visible_change"] = "visible_change"
            observation = (
                f"Формат учебного заключения: оценка соответствия описанию чистой поверхности "
                f"после выше (дельта +{delta:.2f} >= {self.delta_threshold:.2f}). Это не доказательство качества работы."
            )
        else:
            verdict = "no_visible_change"
            observation = (
                f"Статистически значимых видимых изменений поверхности не зафиксировано "
                f"(дельта {delta:.2f} < {self.delta_threshold:.2f})."
            )

        scores = [
            ImageLabelScore(
                photo_id=before_photo_id,
                label=CLEAN_LABEL,
                score=round(float(p_before), 4),
            ),
            ImageLabelScore(
                photo_id=after_photo_id,
                label=CLEAN_LABEL,
                score=round(float(p_after), 4),
            ),
        ]

        return ItemPhotoReview(
            checklist_item_id=checklist_item_id,
            verdict=verdict,
            before_photo_id=before_photo_id,
            after_photo_id=after_photo_id,
            observation=observation,
            scores=scores,
        )
