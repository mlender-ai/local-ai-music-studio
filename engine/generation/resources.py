"""Memory accounting includes macOS compressed/unified allocations."""

import ctypes
import sys
import psutil


class RUsageInfoV2(ctypes.Structure):
    # XNU sys/resource.h: UUID followed by 18 uint64_t fields.
    _fields_ = [("uuid", ctypes.c_uint8 * 16), ("values", ctypes.c_uint64 * 18)]


def process_memory(pid: int) -> tuple[int, int]:
    rss = psutil.Process(pid).memory_info().rss
    footprint = rss
    if sys.platform == "darwin":
        lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        info = RUsageInfoV2()
        lib.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        lib.proc_pid_rusage.restype = ctypes.c_int
        if lib.proc_pid_rusage(pid, 2, ctypes.byref(info)) == 0:
            footprint = max(rss, int(info.values[7]))
    return rss, footprint
