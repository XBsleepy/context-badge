"""Decode PNG/WebP stills through Windows Imaging Component."""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_double, c_void_p, c_ulong, c_uint
from ctypes.wintypes import DWORD, LPCWSTR
from pathlib import Path

ole32 = ctypes.WinDLL("ole32", use_last_error=True)

COINIT_APARTMENTTHREADED = 0x2
CLSCTX_INPROC_SERVER = 0x1
GENERIC_READ = 0x80000000
WICDecodeMetadataCacheOnDemand = 0
S_OK = 0
S_FALSE = 1
RPC_E_CHANGED_MODE = 0x80010106

HRESULT = ctypes.HRESULT


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, text: str = "") -> None:
        super().__init__()
        if not text:
            return
        hexid = text.strip("{}").replace("-", "")
        self.Data1 = int(hexid[0:8], 16)
        self.Data2 = int(hexid[8:12], 16)
        self.Data3 = int(hexid[12:16], 16)
        self.Data4[:] = bytes.fromhex(hexid[16:32])


CLSID_WICImagingFactory = GUID("{CACAF262-9370-4615-A13B-9F5539DA4C0A}")
IID_IWICImagingFactory = GUID("{EC5EC8A9-C395-4314-9E77-C10E32A656F0}")
IID_IWICImagingFactory2 = GUID("{7B816B45-1996-4476-B132-DE9E247C8AF0}")
GUID_WICPixelFormat32bppBGRA = GUID("{6FDDC324-4E03-4BFE-B185-3D77768DC90F}")

ole32.CoInitializeEx.argtypes = [c_void_p, DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoCreateInstance.argtypes = [
    POINTER(GUID),
    c_void_p,
    DWORD,
    POINTER(GUID),
    POINTER(c_void_p),
]
ole32.CoCreateInstance.restype = ctypes.c_long


def _vtable(punk: int) -> ctypes.Array:
    return ctypes.cast(punk, POINTER(POINTER(c_void_p))).contents


def _fn(punk: int, index: int, restype, *argtypes):
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(_vtable(punk)[index])


def _release(punk: int | None) -> None:
    if not punk:
        return
    _fn(punk, 2, c_ulong)(punk)


def _check(hr: int, action: str) -> None:
    value = int(hr)
    if value < 0:
        raise OSError(f"WIC {action} failed: 0x{value & 0xFFFFFFFF:08X}")


def _ensure_com() -> None:
    hr = int(ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
    if hr not in (S_OK, S_FALSE) and (hr & 0xFFFFFFFF) != RPC_E_CHANGED_MODE:
        _check(hr, "CoInitializeEx")


def decode_bgra(path: str | Path) -> tuple[bytes, int, int]:
    """Return straight 32-bit BGRA pixels plus width and height."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    _ensure_com()
    factory = c_void_p()
    decoder = c_void_p()
    frame = c_void_p()
    converter = c_void_p()
    try:
        created = ole32.CoCreateInstance(
            byref(CLSID_WICImagingFactory),
            None,
            CLSCTX_INPROC_SERVER,
            byref(IID_IWICImagingFactory2),
            byref(factory),
        )
        if int(created) < 0:
            created = ole32.CoCreateInstance(
                byref(CLSID_WICImagingFactory),
                None,
                CLSCTX_INPROC_SERVER,
                byref(IID_IWICImagingFactory),
                byref(factory),
            )
        _check(created, "CoCreateInstance")
        factory_ptr = factory.value
        _check(
            _fn(
                factory_ptr,
                3,
                HRESULT,
                LPCWSTR,
                POINTER(GUID),
                DWORD,
                DWORD,
                POINTER(c_void_p),
            )(
                factory_ptr,
                str(source),
                None,
                GENERIC_READ,
                WICDecodeMetadataCacheOnDemand,
                byref(decoder),
            ),
            "CreateDecoderFromFilename",
        )
        decoder_ptr = decoder.value
        _check(
            _fn(decoder_ptr, 13, HRESULT, c_uint, POINTER(c_void_p))(
                decoder_ptr, 0, byref(frame)
            ),
            "GetFrame",
        )
        frame_ptr = frame.value
        _check(
            _fn(factory_ptr, 10, HRESULT, POINTER(c_void_p))(
                factory_ptr, byref(converter)
            ),
            "CreateFormatConverter",
        )
        converter_ptr = converter.value
        _check(
            _fn(
                converter_ptr,
                8,
                HRESULT,
                c_void_p,
                POINTER(GUID),
                c_uint,
                c_void_p,
                c_double,
                c_uint,
            )(
                converter_ptr,
                frame_ptr,
                byref(GUID_WICPixelFormat32bppBGRA),
                0,
                None,
                0.0,
                0,
            ),
            "FormatConverter.Initialize",
        )
        width = c_uint()
        height = c_uint()
        _check(
            _fn(converter_ptr, 3, HRESULT, POINTER(c_uint), POINTER(c_uint))(
                converter_ptr, byref(width), byref(height)
            ),
            "GetSize",
        )
        w = int(width.value)
        h = int(height.value)
        if w <= 0 or h <= 0:
            raise OSError("WIC decoded an empty bitmap")
        stride = w * 4
        buffer = (ctypes.c_ubyte * (stride * h))()
        _check(
            _fn(
                converter_ptr,
                7,
                HRESULT,
                c_void_p,
                c_uint,
                c_uint,
                POINTER(ctypes.c_ubyte),
            )(converter_ptr, None, stride, stride * h, buffer),
            "CopyPixels",
        )
        return bytes(buffer), w, h
    finally:
        _release(converter.value)
        _release(frame.value)
        _release(decoder.value)
        _release(factory.value)
