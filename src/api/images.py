"""Product image access.

Serves the images Phase 1 validated and stored - 43,165 re-encoded 60x80 JPEGs
in `data/processed/images_thumb.parquet`. Nothing is downloaded at runtime and
no second image collection is fetched.

Two tiers, and the store reports honestly which one a product has:

    large   600x800, in `data/processed/images_large/` - present only for
            products that `scripts/fetch_hires_images.py` has been run for,
            because that script fetches per product rather than downloading the
            6.3 GB mirror.
    thumb   60x80, the Phase 1 store - present for all 43,165 products.

`reference()` prefers large and falls back to thumb, so the API improves
automatically as more high-resolution images are fetched and never breaks when
none have been.
"""

from __future__ import annotations

import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_IMAGES = os.path.join(ROOT, "data", "processed", "images_thumb.parquet")
DEFAULT_LARGE_DIR = os.path.join(ROOT, "data", "processed", "images_large")

MEDIA_TYPE = "image/jpeg"


class ImageStore:
    """In-memory image lookup by product id."""

    def __init__(self, path: str | None = None, large_dir: str | None = None,
                 resolver=None):
        self.path = path or DEFAULT_IMAGES
        self.large_dir = large_dir or DEFAULT_LARGE_DIR
        if resolver is None:
            from src.api.image_resolver import ImageResolver

            resolver = ImageResolver(large_dir=self.large_dir)
        self.resolver = resolver
        self._large: dict[int, str] = {}
        self._large_size: dict[int, tuple[int, int]] = {}
        self._large_missing: set[int] = set()
        self._images: dict[int, bytes] = {}
        self._dimensions: dict[int, tuple[int, int]] = {}
        self.available = False
        self.reason: str | None = None

        if not os.path.exists(self.path):
            self.reason = f"image store not found at {self.path}"
            return
        try:
            frame = pd.read_parquet(self.path)
        except Exception as exc:                        # pragma: no cover
            self.reason = f"could not read the image store: {exc}"
            return

        self._images = {
            int(pid): raw for pid, raw in zip(frame.product_id, frame.image_bytes)
        }
        self._dimensions = {
            int(pid): (int(w), int(h))
            for pid, w, h in zip(frame.product_id, frame.width, frame.height)
        }
        self.available = True
        self._index_large()

    def _index_large(self) -> None:
        """Note which products have a high-resolution file on disk."""
        if not os.path.isdir(self.large_dir):
            return
        for filename in os.listdir(self.large_dir):
            stem, extension = os.path.splitext(filename)
            if extension.lower() != ".jpg" or not stem.isdigit():
                continue
            self._large[int(stem)] = os.path.join(self.large_dir, filename)

    @property
    def large_count(self) -> int:
        """How many high-resolution files exist right now.

        Counted from disk rather than from the boot-time index: the index only
        grows lazily as products are requested, so reporting its size would
        under-state coverage whenever images were fetched while the API ran.
        """
        if not os.path.isdir(self.large_dir):
            return 0
        try:
            return sum(1 for f in os.listdir(self.large_dir) if f.endswith(".jpg"))
        except OSError:                      # pragma: no cover - defensive
            return len(self._large)

    def has_large(self, product_id: int) -> bool:
        return self._large_path(int(product_id)) is not None

    def _large_path(self, product_id: int) -> str | None:
        """Path to a high-resolution file, checking disk once on a miss.

        The index is built at startup, but `fetch_hires_images.py` can add files
        while the API is running. Without this, newly fetched images stay
        invisible until a restart.
        """
        pid = int(product_id)
        cached = self._large.get(pid)
        if cached is not None:
            return cached
        if pid in self._large_missing:
            return None
        candidate = os.path.join(self.large_dir, f"{pid}.jpg")
        if os.path.exists(candidate):
            self._large[pid] = candidate
            return candidate
        self._large_missing.add(pid)
        return None

    def _large_dimensions(self, product_id: int) -> tuple[int, int] | None:
        """Read the stored size once, lazily - avoids opening files at boot."""
        pid = int(product_id)
        if pid in self._large_size:
            return self._large_size[pid]
        path = self._large_path(pid)
        if path is None:
            return None
        try:
            from PIL import Image

            with Image.open(path) as image:
                size = (image.width, image.height)
        except Exception:
            return None
        self._large_size[pid] = size
        return size

    def __len__(self) -> int:
        return len(self._images)

    def has(self, product_id: int) -> bool:
        return int(product_id) in self._images

    def get(self, product_id: int, size: str = "auto",
            resolve: bool = False, timeout: float = 12.0) -> bytes | None:
        """Image bytes. `size` is auto (best available), large, or thumb.

        With `resolve`, a product that has no high-resolution file yet is
        fetched now instead of being answered with a 60x80 that the card would
        then have to stretch 4.4x.
        """
        pid = int(product_id)
        if resolve and size in {"auto", "large"} and self.resolver is not None:
            if self.resolver.ensure(pid, timeout, upgrade=True):
                self._large.pop(pid, None)
                self._large_missing.discard(pid)
                self._large_size.pop(pid, None)
        if size in {"auto", "large"}:
            path = self._large_path(pid)
            if path:
                try:
                    with open(path, "rb") as handle:
                        return handle.read()
                except OSError:
                    pass                   # fall through to the thumbnail
        if size == "large":
            return None
        return self._images.get(pid)

    def dimensions(self, product_id: int) -> tuple[int, int] | None:
        return self._dimensions.get(int(product_id))

    def _sharpness(self, product_id: int, path: str) -> dict | None:
        """Measured detail for a stored file, computed once and remembered.

        Pixel count is not quality: some mirror rows are genuinely soft, and a
        900x1200 that carries no more detail than a thumbnail must not be
        presented to a client as a sharp photograph.
        """
        if self.resolver is None:
            return None
        known = self.resolver.quality(product_id)
        if known is not None:
            return known
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.load()
                value = self.resolver.measure(image)
                self.resolver.record_quality(product_id, image.width,
                                             image.height, value)
        except Exception:                              # pragma: no cover
            return None
        return self.resolver.quality(product_id)

    def reference(self, product_id: int) -> dict | None:
        """The image descriptor returned to a client, or None if we have none.

        Returns None rather than a placeholder path when an image is missing -
        a broken URL is worse than an explicit absence.

        `resolution` is the honest state of the photograph:

            large     a genuine high-resolution file is on disk
            pending   none stored yet, but one can be fetched - the image
                      endpoint resolves it when the browser asks for it
            thumb     60x80 is all that will ever exist for this product

        A client must not stretch `thumb` to fill a card. `detail` reports
        whether even a large file actually carries detail.
        """
        pid = int(product_id)
        large = self._large_dimensions(pid)
        if large is not None:
            path = self._large_path(pid)
            quality = self._sharpness(pid, path) if path else None
            return {
                # The resolution is part of the URL so that upgrading a product
                # from thumb to large changes its cache key. Without this, a
                # browser that cached the 60x80 under an `immutable` header
                # keeps showing it for a week even after the large file exists.
                # The width is the version: an upgrade from 600x800 to
                # 900x1200 changes this URL, so a browser holding the older
                # bytes under an `immutable` header cannot keep showing them.
                "url": f"/images/{pid}.jpg?v={large[0]}",
                "width": large[0],
                "height": large[1],
                "media_type": MEDIA_TYPE,
                "resolution": "large",
                "detail": "soft" if quality and not quality.get("sharp") else "sharp",
            }
        size = self._dimensions.get(pid)
        if size is None:
            return None
        if self.resolver is not None and self.resolver.fetchable(pid):
            # Start fetching now. Every path that shows a product - recommend,
            # outfit, browse, detail - goes through here, so one hook keeps
            # coverage complete instead of relying on a pre-fetched list.
            self.resolver.prefetch([pid])
            # Deliberately no width/height: the file does not exist yet, so any
            # number here would be a guess. The card uses its own aspect box.
            return {
                "url": f"/images/{pid}.jpg?v=pending",
                "width": None,
                "height": None,
                "media_type": MEDIA_TYPE,
                "resolution": "pending",
                "detail": "unknown",
            }
        return {
            "url": f"/images/{pid}.jpg?v=thumb",
            "width": size[0],
            "height": size[1],
            "media_type": MEDIA_TYPE,
            "resolution": "thumb",
            "detail": "low",
        }
