"""Lecture de l'en-tête d'un replay Fortnite (quelques octets, sans décompression).

Sert à savoir *immédiatement* si l'enregistrement est terminé :

* ``is_live`` vaut vrai tant que Fortnite enregistre la partie ;
* un replay local est chiffré, et sa clé n'est écrite qu'à la fin de la partie : un replay en cours
  est donc illisible par n'importe quel outil (vérifié dans la bibliothèque de lecture, qui le refuse).

Format (Unreal Engine, ``FLocalFileReplayInfo``) : magie, version, [versions personnalisées],
durée en ms, version réseau, changelist, nom (FString), en direct, horodatage, compressé,
chiffré + clé.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

FILE_MAGIC = 0x1CA2E27F
HISTORY_COMPRESSION = 2
HISTORY_RECORDED_TIMESTAMP = 3
HISTORY_ENCRYPTION = 6
HISTORY_CUSTOM_VERSIONS = 7


@dataclass
class ReplayHeader:
    file_version: int
    length_ms: int
    network_version: int
    changelist: int
    friendly_name: str
    is_live: bool
    is_compressed: bool = False
    is_encrypted: bool = False
    has_key: bool = False

    @property
    def finished(self) -> bool:
        """Enregistrement terminé et lisible (clé présente si le replay est chiffré)."""
        return not self.is_live and (not self.is_encrypted or self.has_key)


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError("en-tête tronqué")
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def fstring(self) -> str:
        n = self.i32()
        if n == 0:
            return ""
        if n < 0:
            raw = self.take(-2 * n)
            return raw.decode("utf-16-le", "replace").replace("\x00", "").strip()
        if n > 4096:
            raise ValueError("nom invalide")
        return self.take(n).decode("latin-1", "replace").replace("\x00", "").strip()


def read_header(path: Path | str, max_bytes: int = 64 * 1024) -> ReplayHeader | None:
    """En-tête du replay, ou None si le fichier n'est pas (encore) un replay lisible."""
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes)
    except OSError:
        return None
    try:
        r = _Reader(data)
        if r.u32() != FILE_MAGIC:
            return None
        version = r.u32()
        if version >= HISTORY_CUSTOM_VERSIONS:
            count = r.i32()
            if not 0 <= count < 1000:
                return None
            r.take(count * 20)
        h = ReplayHeader(file_version=version, length_ms=r.u32(), network_version=r.u32(), changelist=r.u32(),
                         friendly_name=r.fstring(), is_live=r.u32() != 0)
        if version >= HISTORY_RECORDED_TIMESTAMP:
            r.take(8)
        if version >= HISTORY_COMPRESSION:
            h.is_compressed = r.u32() != 0
        if version >= HISTORY_ENCRYPTION:
            h.is_encrypted = r.u32() != 0
            size = r.u32()
            h.has_key = size > 0
        return h
    except (ValueError, struct.error):
        return None
