"""
Tests for NvmlEnergyMeter using a fake pynvml, so they run on any machine.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from sustainability.energy import nvml_meter


class FakeNvml:
    """Minimal pynvml stand-in: energy counter advances 20 W x elapsed time."""

    NVML_TEMPERATURE_GPU = 0
    NVML_CLOCK_SM = 1

    def __init__(self, counter=True, throttle_mask=0, power_mw=20_000):
        self._t0 = time.perf_counter()
        self._counter = counter
        self._throttle = throttle_mask
        self._power = power_mw

    def nvmlInit(self):
        pass

    def nvmlDeviceGetHandleByIndex(self, i):
        return "h"

    def nvmlDeviceGetTotalEnergyConsumption(self, h):
        if not self._counter:
            raise RuntimeError("not supported")
        return int((time.perf_counter() - self._t0) * self._power)  # mJ: mW * s

    def nvmlDeviceGetPowerUsage(self, h):
        self.power_reads = getattr(self, "power_reads", 0) + 1
        return self._power

    def nvmlDeviceGetMemoryInfo(self, h):
        return SimpleNamespace(used=1500 << 20, total=6141 << 20)

    def nvmlDeviceGetTemperature(self, h, kind):
        return 70

    def nvmlDeviceGetClockInfo(self, h, kind):
        return 2100

    def nvmlDeviceGetCurrentClocksThrottleReasons(self, h):
        return self._throttle

    def nvmlDeviceGetPerformanceState(self, h):
        return 8


@pytest.fixture
def fake(monkeypatch):
    def install(**kw):
        f = FakeNvml(**kw)
        monkeypatch.setattr(nvml_meter, "pynvml", f)
        return f
    return install


def test_energy_counter_delta_is_measured(fake):
    fake()
    meter = nvml_meter.NvmlEnergyMeter(sample_interval_s=0.01)
    with meter:
        time.sleep(0.2)
    r = meter.result
    assert r.method == "nvml_energy_counter"
    assert r.measurement_tier == "MEASURED"
    assert r.energy_j == pytest.approx(20.0 * r.duration_s, rel=0.15)
    assert r.peak_mem_used_mib == 1500 and r.max_temp_c == 70
    assert r.n_samples >= 3


def test_falls_back_to_power_sampling_without_counter(fake):
    fake(counter=False)
    meter = nvml_meter.NvmlEnergyMeter(sample_interval_s=0.01)
    with meter:
        time.sleep(0.2)
    assert meter.result.method == "nvml_power_sampling"
    assert meter.result.energy_j == pytest.approx(20.0 * meter.result.duration_s, rel=0.25)


def test_unavailable_never_guesses(monkeypatch):
    monkeypatch.setattr(nvml_meter, "pynvml", None)
    meter = nvml_meter.NvmlEnergyMeter()
    with meter:
        pass
    assert meter.result.method == "unavailable"
    assert meter.result.energy_j is None
    assert meter.result.measurement_tier == "UNAVAILABLE"


def test_thermal_throttle_is_reported(fake):
    fake(throttle_mask=0x40 | 0x04)  # hw thermal slowdown + sw power cap
    meter = nvml_meter.NvmlEnergyMeter(sample_interval_s=0.01)
    with meter:
        time.sleep(0.05)
    assert meter.result.throttle_reasons_seen == ["hw_thermal_slowdown", "sw_power_cap"]


def test_net_energy_subtracts_idle(fake):
    fake()
    meter = nvml_meter.NvmlEnergyMeter(sample_interval_s=0.01)
    with meter:
        time.sleep(0.1)
    r = meter.result
    assert r.net_energy_j(5.0) == pytest.approx(r.energy_j - 5.0 * r.duration_s)
    assert r.net_energy_j(None) is None


def test_counter_measurement_never_polls_power(fake):
    # Polling power perturbs the energy counter on the dev laptop's driver, so a
    # counter-based measurement must not read power at all.
    f = fake()
    meter = nvml_meter.NvmlEnergyMeter(sample_interval_s=0.01)
    with meter:
        time.sleep(0.1)
    assert getattr(f, "power_reads", 0) == 0
    assert meter.result.counter_reads == 2


def test_wait_for_gpu_idle_settles_on_idle_pstate(fake):
    f = fake()
    info = nvml_meter.wait_for_gpu_idle(max_wait_s=2, window=3, interval_s=0.01)
    assert info["settled"] is True and info["pstate"] == 8
    assert getattr(f, "power_reads", 0) == 0
