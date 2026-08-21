"""Obtain a genuine high-resolution image for any product, on demand.

Phase 1 stored a 60x80 thumbnail for all 43,165 products - enough to prove the
catalog, far too small for a product card. `scripts/fetch_hires_images.py` could
pull real photography, but only for an explicit list, so coverage sat at 663
products (1.5%). Every other product was a 60x80 stretched 4.4x into a 278x351
card, which is exactly what "blurry" looked like.

This module removes the list. Every catalog product has a row in
`image_fetch_index.csv`, so any product can be resolved when it is actually
needed:

    prefetch(ids)      queue missing images, return immediately
    ensure(pid, t)     block up to `t` seconds for one image

The image endpoint calls `ensure`, so a card that was recommended before its
photograph existed still paints a real one - the browser waits on the image
request rather than on the recommendation. Results are written to disk, so a
product is fetched once and then costs nothing.

Sources are not uniformly good. Some mirror rows are genuinely soft, and no
amount of resizing invents detail, so each stored file records a measured
sharpness and the API reports it rather than implying every 900x1200 is sharp.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(ROOT, "data", "processed", "image_fetch_index.csv")
LARGE_DIR = os.path.join(ROOT, "data", "processed", "images_large")

MIRROR = "benitomartin/fashion-product-images-small-900x1200"
ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"

# The mirror is natively 900x1200. Phase 5 downsampled it to 600x800, which is
# below what a 460px detail hero needs on a 2x display, so the native size is
# kept and the browser performs the only downscale.
TARGET_SIZE = (900, 1200)
JPEG_QUALITY = 86

WORKERS = 3            # measured: 8 workers produced a wave of HTTP 429s
TIMEOUT = 30
RETRIES = 3
BACKOFF = 2.0

# A results page asks for ~24 images at once. Without a ceiling those become 24
# simultaneous mirror requests and the mirror answers with 429s, so every card
# fails at once. Requests that cannot get a slot fall back to the thumbnail and
# the background queue picks them up.
MAX_CONCURRENT_FETCHES = 4

# Below this, a source carries no more detail than a small thumbnail however
# many pixels it claims. Calibrated against the store: genuine photography
# measures 300-3000, while known-soft rows measure 3-70.
SHARPNESS_FLOOR = 80.0


def _disabled() -> bool:
    """Tests and offline runs must never reach the network."""
    return os.environ.get("DISABLE_IMAGE_FETCH") == "1"


class ImageResolver:
    """Fetches, stores and grades high-resolution product photography."""

    def __init__(self, large_dir: str | None = None, index: str | None = None):
        self.large_dir = large_dir or LARGE_DIR
        self.index_path = index or INDEX
        self._offsets: dict[int, int] = {}
        self._quality: dict[int, dict] = {}
        self._unavailable: set[int] = set()
        self._locks: dict[int, threading.Lock] = {}
        self._guard = threading.Lock()
        self._queued: set[int] = set()
        self._slots = threading.Semaphore(MAX_CONCURRENT_FETCHES)
        self._pool: ThreadPoolExecutor | None = None
        self.enabled = False
        self.reason: str | None = None
        self._load()

    # ---------------------------------------------------------------- setup
    def _load(self) -> None:
        os.makedirs(self.large_dir, exist_ok=True)
        quality = self._read_json(self._sidecar_path(), {})
        self._quality = {int(k): v for k, v in quality.items()}
        self._unavailable = {int(p) for p in
                             self._read_json(self._unavailable_path(), [])}
        if not os.path.exists(self.index_path):
            self.reason = f"fetch index not found at {self.index_path}"
            return
        try:
            import pandas as pd

            frame = pd.read_csv(self.index_path)
            self._offsets = dict(zip(frame.product_id.astype(int),
                                     frame.source_row_index.astype(int)))
        except Exception as exc:                          # pragma: no cover
            self.reason = f"could not read the fetch index: {exc}"
            return
        self.enabled = True

    def _sidecar_path(self) -> str:
        return os.path.join(self.large_dir, "_quality.json")

    def _unavailable_path(self) -> str:
        return os.path.join(self.large_dir, "_unavailable.json")

    @staticmethod
    def _read_json(path: str, default):
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return default

    def _write_json(self, path: str, payload) -> None:
        staging = path + ".part"
        try:
            with open(staging, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            os.replace(staging, path)
        except OSError:                                   # pragma: no cover
            pass

    # ------------------------------------------------------------- querying
    def fetchable(self, product_id: int) -> bool:
        """Whether a genuine photograph could still be obtained."""
        pid = int(product_id)
        return (self.enabled and not _disabled()
                and pid in self._offsets and pid not in self._unavailable)

    def path(self, product_id: int) -> str | None:
        candidate = os.path.join(self.large_dir, f"{int(product_id)}.jpg")
        return candidate if os.path.exists(candidate) else None

    def is_undersized(self, product_id: int) -> bool:
        """Whether a stored file is smaller than the mirror can supply.

        An earlier script stored images at 600x800. That is enough for a card
        at 1x but leaves no headroom on a scaled display, so those files read as
        soft next to the 900x1200 ones. Such a file is re-fetched the next time
        it is actually asked for, rather than in a bulk sweep.
        """
        path = self.path(product_id)
        if path is None:
            return False
        known = self.quality(product_id)
        width = known.get("width") if known else None
        if width is None:
            try:
                from PIL import Image

                with Image.open(path) as image:
                    width = image.width
            except Exception:                             # pragma: no cover
                return False
        return width < TARGET_SIZE[0]

    def quality(self, product_id: int) -> dict | None:
        """Measured facts about a stored file: its size and whether it is sharp."""
        return self._quality.get(int(product_id))

    def record_quality(self, product_id: int, width: int, height: int,
                       sharpness: float) -> None:
        """Note a measurement for a file that was already on disk."""
        self._quality[int(product_id)] = {
            "width": int(width), "height": int(height),
            "sharpness": round(float(sharpness), 1),
            "sharp": float(sharpness) >= SHARPNESS_FLOOR,
        }
        self._write_json(self._sidecar_path(),
                         {str(k): v for k, v in self._quality.items()})

    # ------------------------------------------------------------- fetching
    def _lock_for(self, pid: int) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(pid, threading.Lock())

    def _get(self, url: str) -> bytes:
        last: Exception | None = None
        for attempt in range(RETRIES):
            try:
                return urllib.request.urlopen(url, timeout=TIMEOUT).read()
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code not in (429, 500, 502, 503, 504):
                    raise
            except Exception as exc:
                last = exc
            time.sleep(BACKOFF * (attempt + 1))
        raise last if last else RuntimeError("request failed")

    def measure(self, image) -> float:
        """High-frequency energy - how much real detail the picture holds."""
        try:
            import numpy as np
            from numpy.lib.stride_tricks import sliding_window_view
            from PIL import Image as PILImage

            grey = np.asarray(
                image.convert("L").resize((300, 400), PILImage.LANCZOS),
                dtype=np.float32)
            kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
            windows = sliding_window_view(grey, (3, 3))
            return float((windows * kernel).sum(axis=(-1, -2)).var())
        except Exception:                                 # pragma: no cover
            return SHARPNESS_FLOOR + 1.0

    def _fetch(self, product_id: int) -> str | None:
        """Download, store and grade one product. Returns the path or None."""
        import io

        from PIL import Image

        pid = int(product_id)
        destination = os.path.join(self.large_dir, f"{pid}.jpg")
        offset = self._offsets.get(pid)
        if offset is None:
            return None

        url = (f"{ROWS_ENDPOINT}?dataset={urllib.parse.quote(MIRROR)}"
               f"&config=default&split=train&offset={offset}&length=1")
        payload = json.loads(self._get(url))
        row = payload["rows"][0]["row"]
        if int(row["id"]) != pid:
            raise ValueError(f"mirror row {offset} holds id {row['id']}, not {pid}")

        raw = self._get(row["image"]["src"])
        staging = destination + ".part"
        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("RGB")
            # thumbnail() only ever shrinks, so a small source is never blown
            # up to fake a high resolution.
            image.thumbnail(TARGET_SIZE, Image.LANCZOS)
            sharpness = self.measure(image)
            image.save(staging, "JPEG", quality=JPEG_QUALITY, optimize=True)
            width, height = image.width, image.height
        os.replace(staging, destination)
        self.record_quality(pid, width, height, sharpness)
        return destination

    def _mark_unavailable(self, pid: int) -> None:
        self._unavailable.add(pid)
        self._write_json(self._unavailable_path(), sorted(self._unavailable))

    def ensure(self, product_id: int, timeout: float = 12.0,
               upgrade: bool = False) -> str | None:
        """Return a path to a genuine image, fetching it if necessary.

        With `upgrade`, a stored file that is smaller than the mirror can supply
        is replaced with the full-size one.
        """
        pid = int(product_id)
        existing = self.path(pid)
        wants_upgrade = upgrade and self.fetchable(pid) and self.is_undersized(pid)
        if existing and not wants_upgrade:
            return existing
        if not self.fetchable(pid):
            return existing

        deadline = time.monotonic() + max(0.1, timeout)
        lock = self._lock_for(pid)
        if not lock.acquire(timeout=max(0.1, timeout)):
            return self.path(pid)                 # another thread is already on it
        try:
            existing = self.path(pid)
            if existing and not wants_upgrade:
                return existing
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._slots.acquire(timeout=remaining):
                # Too busy right now. Whatever is on disk beats nothing.
                return existing
            try:
                return self._fetch(pid)
            finally:
                self._slots.release()
        except Exception:
            if existing is None:
                self._mark_unavailable(pid)
            return existing
        finally:
            lock.release()

    # ----------------------------------------------------------- prefetching
    def prefetch(self, product_ids) -> int:
        """Queue missing images without blocking the caller."""
        if not self.enabled or _disabled():
            return 0
        missing = [int(p) for p in product_ids
                   if self.fetchable(p) and self.path(p) is None]
        if not missing:
            return 0
        with self._guard:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=WORKERS,
                                                thread_name_prefix="imgfetch")
            fresh = [p for p in missing if p not in self._queued]
            self._queued.update(fresh)
            pool = self._pool
        for pid in fresh:
            pool.submit(self._background, pid)
        return len(fresh)

    def _background(self, pid: int) -> None:
        try:
            self.ensure(pid, timeout=60.0)
        finally:
            with self._guard:
                self._queued.discard(pid)

    @property
    def pending(self) -> int:
        with self._guard:
            return len(self._queued)

    @property
    def stored(self) -> int:
        try:
            return sum(1 for f in os.listdir(self.large_dir) if f.endswith(".jpg"))
        except OSError:                                   # pragma: no cover
            return 0
