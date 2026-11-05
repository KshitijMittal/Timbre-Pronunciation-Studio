from __future__ import annotations

import os
import threading
from pathlib import Path
from uuid import uuid4

# Windows refuses to replace a file another thread is replacing. One lock keeps
# same-target writers in this process serialised; the unique temp name keeps two
# processes from sharing (and losing) one temp file.
_REPLACE_LOCK = threading.Lock()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(data)
        with _REPLACE_LOCK:
            os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
