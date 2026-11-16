"""Binary result container ("EMF1").

Layout (all little-endian):

    bytes 0..3    magic  b"EMF1"
    bytes 4..7    uint32 header_length (bytes of UTF-8 JSON)
    bytes 8..     JSON header (the ResultHeader, including the array table)
    padding       zero bytes up to the next multiple of 8
    payload       raw arrays; each array's ``offset`` is relative to the payload start and is
                  a multiple of 8, so typed-array views can be created without copying.

Fields are computed in float64 and transported as float32 (``<f4``). Statistics that need full
precision (min/max of magnitudes) are computed in float64 and carried in the JSON header.
"""

from __future__ import annotations

import json
import struct
from typing import Any

import numpy as np
from numpy.typing import NDArray

MAGIC = b"EMF1"
_ALIGN = 8


def _pad(n: int) -> int:
    return (-n) % _ALIGN


def encode(header: dict[str, Any], arrays: dict[str, NDArray[Any]]) -> bytes:
    """Serialize. ``header["arrays"]`` must list entries whose ``name`` keys match ``arrays``;
    this function fills in dtype, shape, offset and byte_length."""
    table = header.get("arrays", [])
    names = [e["name"] for e in table]
    if sorted(names) != sorted(arrays):
        raise ValueError("header array table does not match the provided arrays")
    chunks: list[bytes] = []
    offset = 0
    for entry in table:
        arr = np.ascontiguousarray(arrays[entry["name"]], dtype="<f4")
        raw = arr.tobytes()
        entry.update(dtype="<f4", shape=list(arr.shape), offset=offset, byte_length=len(raw))
        pad = _pad(len(raw))
        chunks.append(raw + b"\x00" * pad)
        offset += len(raw) + pad
    # allow_nan=False: NaN/Inf must never leak into JSON (payload arrays may contain NaN masks).
    head = json.dumps(header, allow_nan=False, separators=(",", ":")).encode("utf-8")
    prefix = MAGIC + struct.pack("<I", len(head)) + head
    return prefix + b"\x00" * _pad(len(prefix)) + b"".join(chunks)


def decode(blob: bytes) -> tuple[dict[str, Any], dict[str, NDArray[np.float32]]]:
    if blob[:4] != MAGIC:
        raise ValueError("not an EMF1 container")
    (hlen,) = struct.unpack("<I", blob[4:8])
    header: dict[str, Any] = json.loads(blob[8 : 8 + hlen].decode("utf-8"))
    start = 8 + hlen + _pad(8 + hlen)
    arrays: dict[str, NDArray[np.float32]] = {}
    for e in header.get("arrays", []):
        a = np.frombuffer(blob, dtype=e["dtype"], count=int(np.prod(e["shape"], dtype=np.int64)),
                          offset=start + e["offset"])
        arrays[e["name"]] = a.reshape(e["shape"])
    return header, arrays


def read_header(blob: bytes) -> dict[str, Any]:
    if blob[:4] != MAGIC:
        raise ValueError("not an EMF1 container")
    (hlen,) = struct.unpack("<I", blob[4:8])
    result: dict[str, Any] = json.loads(blob[8 : 8 + hlen].decode("utf-8"))
    return result
