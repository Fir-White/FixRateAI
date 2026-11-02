"""CLIP Zero-Shot classifier for before/after maintenance photo comparison."""
from __future__ import annotations

import io
from typing import Literal
from uuid import UUID
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
        revision: str = settings.clip_revision,
        delta_threshold: float = settings.clip_delta_threshold,
        prompt_set_version: str = settings.prompt_set_version,
    ):
        self.model_name = model_name
        self.revision = revision
        self.delta_threshold = delta_threshold
        self.prompt_set_version = prompt_set_version
        self._processor = None
        self._model = None
        self._is_torch_available = False
        self._initialized = False
        self._cached_text_features = None

    def _init_backend(self) -> None:
        """Attempt to load transformers and torch if available."""
        self._initialized = True
        try:
            import torch
            from transformers import AutoProcessor, CLIPModel
            self._processor = AutoProcessor.from_pretrained(self.model_name, revision=self.revision, local_files_only=True)
            self._model = CLIPModel.from_pretrained(self.model_name, revision=self.revision, local_files_only=True)
            self._model.eval()
            self._is_torch_available = True
        except Exception:
            self._is_torch_available = False

    @property
    def is_torch_active(self) -> bool:
        if not self._initialized:
            self._init_backend()
        return self._is_torch_available and self._model is not None

    @property
    def model_ref(self) -> str:
        revision = getattr(getattr(self._model, "config", None), "_commit_hash", None)
        return f"{self.model_name}@{revision or self.revision}"

    def warmup(self) -> bool:
        """Pre-load weights and cache static prompt embeddings."""
        if not self.is_torch_active:
            return False
        try:
            self._get_text_features()
            return True
        except Exception:
            return False

    def _get_text_features(self):
        """Compute and cache normalized text embeddings for DEFAULT_PROMPTS."""
        if self._cached_text_features is None:
            if not self.is_torch_active:
                raise RuntimeError("CLIP model unavailable")
            import torch
            inputs = self._processor(text=DEFAULT_PROMPTS, return_tensors="pt", padding=True)
            with torch.no_grad():
                if hasattr(self._model, "get_text_features"):
                    text_features = self._model.get_text_features(**inputs)
                    self._cached_text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                else:
                    self._cached_text_features = None
        return self._cached_text_features

    def _infer_batch(self, images_bytes: list[bytes]) -> list[float]:
        """Infer relative clean prompt scores for a batch of images in a single forward pass."""
        if not images_bytes:
            return []
        if not self.is_torch_active:
            raise RuntimeError("CLIP model unavailable")

        import torch

        pil_images = []
        for b in images_bytes:
            with Image.open(io.BytesIO(b)) as pil_img:
                pil_images.append(pil_img.convert("RGB"))

        text_features = self._get_text_features()

        with torch.no_grad():
            if text_features is not None and hasattr(self._model, "get_image_features"):
                inputs = self._processor(images=pil_images, return_tensors="pt")
                image_features = self._model.get_image_features(**inputs)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                logit_scale = self._model.logit_scale.exp()
                logits = logit_scale * (image_features @ text_features.t())
                probs = logits.softmax(dim=1).cpu().numpy()
                return [float(p[1]) for p in probs]
            else:
                inputs = self._processor(
                    text=DEFAULT_PROMPTS,
                    images=pil_images,
                    return_tensors="pt",
                    padding=True,
                )
                outputs = self._model(**inputs)
                logits = outputs.logits_per_image
                probs = logits.softmax(dim=1).cpu().numpy()
                return [float(p[1]) for p in probs]

    def _infer_single_image(self, image_bytes: bytes) -> float:
        """Return relative prompt score, not a calibrated cleanliness probability."""
        return self._infer_batch([image_bytes])[0]

    def evaluate_pair(
        self,
        checklist_item_id: UUID,
        before_photo_id: UUID,
        after_photo_id: UUID,
        before_bytes: bytes,
        after_bytes: bytes,
    ) -> ItemPhotoReview:
        """Evaluate a pair of before/after photos and return structured item review."""
        scores = self._infer_batch([before_bytes, after_bytes])
        p_before, p_after = scores[0], scores[1]

        delta = p_after - p_before

        if delta >= self.delta_threshold:
            verdict: Literal["visible_change", "no_visible_change", "uncertain"] = "visible_change"
            observation = (
                f"Формат учебного заключения: оценка соответствия описанию чистой поверхности "
                f"после выше (дельта +{delta:.2f} >= {self.delta_threshold:.2f}). Это не доказательство качества работы."
            )
        elif delta <= -self.delta_threshold:
            verdict = "uncertain"
            observation = "Сходство с описанием чистой поверхности уменьшилось; требуется ручной осмотр."
        else:
            verdict = "no_visible_change"
            observation = (
                f"Рост сходства с описанием чистой поверхности не достиг порога "
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
