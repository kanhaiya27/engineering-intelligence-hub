"""
Engineering Intelligence Hub — NVML energy meter
=================================================
Measures GPU energy for a block of work from the driver's cumulative energy
counter (`nvmlDeviceGetTotalEnergyConsumption`, millijoules), which integrates
power inside the driver. This is a MEASURED quantity: no TDP proxy and no
single-sample power x duration extrapolation.

A background thread samples power, device memory, temperature, SM clock and
clock-throttle reasons while the block runs, so peak VRAM and thermal or power
throttling are visible in the record of every measurement.

Fallbacks, always labelled in `method`:
  * "nvml_energy_counter"  — counter delta (preferred)
  * "nvml_power_sampling"  — trapezoid integral of sampled power, used only when
                             the GPU does not expose the energy counter
  * "unavailable"          — no NVML; energy_j is None (never a guess)

System boundary: GPU board energy only. CPU, RAM and the rest of the machine are
not included. Gross energy includes the GPU's idle draw for the duration; use
`net_energy_j(idle_power_w)` to subtract a separately measured idle baseline.

Windows note: under the WDDM driver, NVML does not report per-process GPU memory,
so memory figures are DEVICE-WIDE (all processes, including the desktop).
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - import guard exercised implicitly on machines without NVIDIA
    import pynvml  # type: ignore[import]
except Exception:  # noqa: BLE001
    pynvml = None  # type: ignore[assignment]

# Bits of nvmlDeviceGetCurrentClocksThrottleReasons that indicate the GPU was
# held back by heat or power rather than simply being idle.
_THROTTLE_BITS = {
    0x0000000000000004: "sw_power_cap",
    0x0000000000000008: "hw_slowdown",
    0x0000000000000020: "sw_thermal_slowdown",
    0x0000000000000040: "hw_thermal_slowdown",
    0x0000000000000080: "hw_power_brake_slowdown",
}


@dataclass
class GpuSample:
    t_s: float
    power_w: Optional[float]
    mem_used_mib: Optional[int]
    temp_c: Optional[int]
    sm_clock_mhz: Optional[int]
    throttle_mask: Optional[int]


@dataclass
class EnergyMeasurement:
    method: str
    measurement_tier: str
    duration_s: float
    energy_j: Optional[float]
    mean_power_w: Optional[float]
    peak_mem_used_mib: Optional[int]
    start_mem_used_mib: Optional[int]
    max_temp_c: Optional[int]
    min_sm_clock_mhz: Optional[int]
    max_sm_clock_mhz: Optional[int]
    throttle_reasons_seen: List[str] = field(default_factory=list)
    n_samples: int = 0

    def net_energy_j(self, idle_power_w: Optional[float]) -> Optional[float]:
        """Gross energy minus idle draw over the same duration (DERIVED)."""
        if self.energy_j is None or idle_power_w is None:
            return None
        return self.energy_j - idle_power_w * self.duration_s

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def nvml_available() -> bool:
    if pynvml is None:
        return False
    try:
        pynvml.nvmlInit()
        pynvml.nvmlDeviceGetHandleByIndex(0)
        return True
    except Exception:  # noqa: BLE001
        return False


class NvmlEnergyMeter:
    """
    Context manager measuring one block of GPU work.

        with NvmlEnergyMeter() as meter:
            run_generation()
        m = meter.result   # EnergyMeasurement
    """

    def __init__(self, device_index: int = 0, sample_interval_s: float = 0.05) -> None:
        self.device_index = device_index
        self.sample_interval_s = sample_interval_s
        self.samples: List[GpuSample] = []
        self.result: Optional[EnergyMeasurement] = None
        self._handle = None
        self._counter_ok = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._t0 = 0.0
        self._e0_mj: Optional[int] = None

        if nvml_available():
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
            try:
                pynvml.nvmlDeviceGetTotalEnergyConsumption(self._handle)
                self._counter_ok = True
            except Exception:  # noqa: BLE001 - counter unsupported on this GPU
                self._counter_ok = False

    # -- sampling -----------------------------------------------------------
    def _read(self, fn, *args):
        try:
            return fn(self._handle, *args)
        except Exception:  # noqa: BLE001
            return None

    def _sample(self) -> GpuSample:
        power = self._read(pynvml.nvmlDeviceGetPowerUsage)
        mem = self._read(pynvml.nvmlDeviceGetMemoryInfo)
        return GpuSample(
            t_s=time.perf_counter() - self._t0,
            power_w=power / 1000.0 if power is not None else None,
            mem_used_mib=(mem.used >> 20) if mem is not None else None,
            temp_c=self._read(pynvml.nvmlDeviceGetTemperature, pynvml.NVML_TEMPERATURE_GPU),
            sm_clock_mhz=self._read(pynvml.nvmlDeviceGetClockInfo, pynvml.NVML_CLOCK_SM),
            throttle_mask=self._read(pynvml.nvmlDeviceGetCurrentClocksThrottleReasons),
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            self.samples.append(self._sample())
            self._stop.wait(self.sample_interval_s)

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "NvmlEnergyMeter":
        self._t0 = time.perf_counter()
        if self._handle is not None:
            self.samples.append(self._sample())
            if self._counter_ok:
                self._e0_mj = pynvml.nvmlDeviceGetTotalEnergyConsumption(self._handle)
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        duration = time.perf_counter() - self._t0
        e1_mj = None
        if self._handle is not None and self._counter_ok:
            e1_mj = pynvml.nvmlDeviceGetTotalEnergyConsumption(self._handle)
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._handle is not None:
            self.samples.append(self._sample())
        self.result = self._summarise(duration, e1_mj)

    # -- summary ------------------------------------------------------------
    def _summarise(self, duration: float, e1_mj: Optional[int]) -> EnergyMeasurement:
        powers = [(s.t_s, s.power_w) for s in self.samples if s.power_w is not None]
        mems = [s.mem_used_mib for s in self.samples if s.mem_used_mib is not None]
        temps = [s.temp_c for s in self.samples if s.temp_c is not None]
        clocks = [s.sm_clock_mhz for s in self.samples if s.sm_clock_mhz is not None]
        throttles = sorted(
            {name for s in self.samples if s.throttle_mask
             for bit, name in _THROTTLE_BITS.items() if s.throttle_mask & bit}
        )

        if self._handle is None:
            method, energy = "unavailable", None
        elif self._counter_ok and self._e0_mj is not None and e1_mj is not None:
            method, energy = "nvml_energy_counter", (e1_mj - self._e0_mj) / 1000.0
        elif len(powers) >= 2:
            method = "nvml_power_sampling"
            energy = sum((t1 - t0) * (p0 + p1) / 2 for (t0, p0), (t1, p1) in zip(powers, powers[1:]))
        else:
            method, energy = "unavailable", None

        return EnergyMeasurement(
            method=method,
            measurement_tier="MEASURED" if energy is not None else "UNAVAILABLE",
            duration_s=duration,
            energy_j=energy,
            mean_power_w=(energy / duration) if energy is not None and duration > 0 else None,
            peak_mem_used_mib=max(mems) if mems else None,
            start_mem_used_mib=mems[0] if mems else None,
            max_temp_c=max(temps) if temps else None,
            min_sm_clock_mhz=min(clocks) if clocks else None,
            max_sm_clock_mhz=max(clocks) if clocks else None,
            throttle_reasons_seen=throttles,
            n_samples=len(self.samples),
        )


def wait_for_gpu_idle(
    max_wait_s: float = 60.0,
    window: int = 8,
    tolerance_w: float = 1.5,
    interval_s: float = 0.5,
    device_index: int = 0,
) -> Dict[str, Any]:
    """
    Block until GPU board power has settled, so an idle baseline is not taken
    while the GPU is still in its high-performance state after a workload.

    Settled = the last `window` power samples lie within `tolerance_w` of each
    other. Laptop GPUs can stay at P0 for many seconds after work ends; an idle
    window measured then reads several times the true idle draw.
    """
    if not nvml_available():
        return {"settled": False, "waited_s": 0.0, "power_w": None, "pstate": None, "reason": "no_nvml"}
    h = pynvml.nvmlDeviceGetHandleByIndex(device_index)
    powers: List[float] = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < max_wait_s:
        powers.append(pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0)
        recent = powers[-window:]
        if len(recent) == window and max(recent) - min(recent) <= tolerance_w:
            break
        time.sleep(interval_s)
    recent = powers[-window:]
    try:
        pstate = pynvml.nvmlDeviceGetPerformanceState(h)
    except Exception:  # noqa: BLE001
        pstate = None
    return {
        "settled": len(recent) == window and max(recent) - min(recent) <= tolerance_w,
        "waited_s": round(time.perf_counter() - t0, 2),
        "power_w": round(sum(recent) / len(recent), 2) if recent else None,
        "power_spread_w": round(max(recent) - min(recent), 2) if recent else None,
        "pstate": pstate,
    }


def measure_idle_power(seconds: float = 10.0, device_index: int = 0) -> Optional[float]:
    """Mean GPU board power over an idle window, from the energy counter (MEASURED)."""
    meter = NvmlEnergyMeter(device_index=device_index, sample_interval_s=0.25)
    with meter:
        time.sleep(seconds)
    return meter.result.mean_power_w if meter.result else None
