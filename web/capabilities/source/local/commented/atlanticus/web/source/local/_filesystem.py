# Primitivas internas de filesystem del proveedor Local.
# Aquí viven exclusión mutua entre procesos, escrituras durables y codificación segura de segmentos físicos.
from __future__ import annotations

import base64
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import TracebackType
from typing import BinaryIO


# Lock por Source para que compare + promoción de manifest sea una sección crítica real.
class SourceFileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._stream: BinaryIO | None = None

    def __enter__(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        stream = self._path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt

                if stream.seek(0, os.SEEK_END) == 0:
                    stream.write(b'\0')
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            if os.name == 'nt':
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
            self._stream = None


def encode_segment(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode('utf-8')).decode('ascii').rstrip('=')


def write_new_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


# Reemplaza el archivo completo y sincroniza el directorio para preservar el commit point.
def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def fsync_directory(path: Path) -> None:
    if os.name == 'nt':
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def remove_temporary_tree(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)
