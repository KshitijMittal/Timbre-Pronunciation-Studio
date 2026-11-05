from __future__ import annotations

from threading import Thread
from pathlib import Path

from app.core.atomic import atomic_write_bytes


def test_concurrent_writes_to_one_target_all_land(tmp_path: Path):
    """Six threads saved the same file turned into 5 PermissionError and no file."""
    target = tmp_path / "same.bin"
    errors: list[Exception] = []

    def write(tag: int) -> None:
        try:
            atomic_write_bytes(target, bytes([tag]) * 100_000)
        except Exception as exc:  # noqa: BLE001 - collected for the assertion
            errors.append(exc)

    threads = [Thread(target=write, args=(tag,)) for tag in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    data = target.read_bytes()
    assert len(data) == 100_000
    assert len(set(data)) == 1, "one writer's bytes must win whole, never a mix"
    assert list(tmp_path.glob("*.tmp")) == []
