"""Image quality assessment and sanity checks (Laplacian variance, contrast, brightness)."""
from __future__ import annotations

import hashlib
import io
from typing import Literal
import numpy as np
from PIL import Image, ImageStat

from ml_service.app.core.config import settings
from ml_service.app.schemas import PhotoReport


class ImageQualityResult:
    def __init__(
        self,
        is_acceptable: bool,
        issue: str | None = None,
        laplacian_var: float = 0.0,
        mean_brightness: float = 0.0,
        sha256: str = "",
    ):
        self.is_acceptable = is_acceptable
        self.issue = issue
        self.laplacian_var = laplacian_var
        self.mean_brightness = mean_brightness
        self.sha256 = sha256


class ImageQualityGuard:
    """Pre-inference technical filter checking sharpness, lighting, and integrity."""

    def __init__(
        self,
        min_laplacian_var: float = settings.laplacian_variance_threshold,
        min_brightness: float = settings.brightness_min,
        max_brightness: float = settings.brightness_max,
        max_bytes: int = settings.image_max_bytes,
        max_pixels: int = settings.image_max_pixels,
    ):
        self.min_laplacian_var = min_laplacian_var
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels

    def assess_bytes(self, image_bytes: bytes) -> ImageQualityResult:
        """Inspect raw image bytes and return quality verdict and metrics."""
        # 1. Size check
        if len(image_bytes) == 0:
            return ImageQualityResult(False, "Файл пуст (0 байт)")
        if len(image_bytes) > self.max_bytes:
            return ImageQualityResult(False, f"Превышен лимит размера файла ({len(image_bytes)} > {self.max_bytes} байт)")

        # 2. SHA-256 calculation
        content_sha256 = hashlib.sha256(image_bytes).hexdigest()

        # 3. Pillow decode and dimension checks
        try:
            with Image.open(io.BytesIO(image_bytes)) as pil_img:
                width, height = pil_img.size
                if width * height > self.max_pixels:
                    return ImageQualityResult(
                        False,
                        f"Разрешение превышает допустимый предел ({width}x{height} > {self.max_pixels} пикс)",
                        sha256=content_sha256,
                    )

                # Convert to 8-bit grayscale
                gray = pil_img.convert("L")
                # Direct C-level mean brightness without array allocation
                mean_brightness = float(ImageStat.Stat(gray).mean[0])

                # Downsample large images (>512px) for Laplacian sharpness check to limit RAM and CPU spikes
                max_dim = max(width, height)
                if max_dim > 512:
                    scale = 512.0 / max_dim
                    target_w = max(3, int(width * scale))
                    target_h = max(3, int(height * scale))
                    gray_sharp = gray.resize((target_w, target_h), Image.Resampling.BILINEAR)
                else:
                    gray_sharp = gray

                arr = np.array(gray_sharp, dtype=np.float32)

        except Exception as exc:
            return ImageQualityResult(False, f"Ошибка декодирования изображения: {type(exc).__name__}", sha256=content_sha256)

        # 4. Brightness check
        if mean_brightness < self.min_brightness:
            return ImageQualityResult(
                False,
                f"Недостаточная освещённость (яркость {mean_brightness:.1f} < {self.min_brightness})",
                mean_brightness=mean_brightness,
                sha256=content_sha256,
            )
        if mean_brightness > self.max_brightness:
            return ImageQualityResult(
                False,
                f"Пересвет вспышкой (яркость {mean_brightness:.1f} > {self.max_brightness})",
                mean_brightness=mean_brightness,
                sha256=content_sha256,
            )

        # Central ROI check catches local glare hidden by a plausible whole-frame mean.
        # Threshold is a technical capture filter, not a probability of correct maintenance.
        h,w=arr.shape
        roi=arr[h//4:max(h//4+1,3*h//4),w//4:max(w//4+1,3*w//4)]
        from scipy.ndimage import label
        components,count=label(roi>=250)
        areas=np.bincount(components.ravel())[1:]
        glare_fraction=float(areas.max()/roi.size) if count else 0.0
        if glare_fraction>0.02:
            return ImageQualityResult(False,f"Блик в центральной области ({glare_fraction:.1%}); измените ракурс и переснимите",mean_brightness=mean_brightness,sha256=content_sha256)

        # 5. Sharpness check: 2D discrete Laplacian variance
        if arr.shape[0] >= 3 and arr.shape[1] >= 3:
            lap = arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:] - 4.0 * arr[1:-1, 1:-1]
            lap_var = float(np.var(lap))
        else:
            lap_var = 0.0

        if lap_var < self.min_laplacian_var:
            return ImageQualityResult(
                False,
                f"Изображение смазано (резкость {lap_var:.1f} < {self.min_laplacian_var})",
                laplacian_var=lap_var,
                mean_brightness=mean_brightness,
                sha256=content_sha256,
            )

        return ImageQualityResult(
            True,
            None,
            laplacian_var=lap_var,
            mean_brightness=mean_brightness,
            sha256=content_sha256,
        )

    def verify_pair_consistency(
        self,
        before_report: PhotoReport,
        after_report: PhotoReport,
        before_bytes: bytes,
        after_bytes: bytes,
    ) -> tuple[bool, str | None]:
        """Verify that before and after photos form a valid, non-identical pair."""
        # 1. View key check
        if before_report.view_key != after_report.view_key:
            return False, f"Несовпадающий ракурс съемки: '{before_report.view_key}' != '{after_report.view_key}'"

        # 2. Identical hash check
        if before_report.original_sha256 == after_report.original_sha256:
            return False, "Обнаружены идентичные фотографии для фаз 'до' и 'после' (одинаковый SHA-256)"

        # 3. Byte level comparison (fast short-circuit by length before SHA-256 hashing)
        if len(before_bytes) == len(after_bytes):
            hash_before = hashlib.sha256(before_bytes).hexdigest()
            hash_after = hashlib.sha256(after_bytes).hexdigest()
            if hash_before == hash_after:
                return False, "Обнаружено тождественное содержимое файлов для фаз 'до' и 'после'"

        return True, None
