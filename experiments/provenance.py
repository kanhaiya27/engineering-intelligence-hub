"""
Engineering Intelligence Hub — run provenance
=============================================
`collect_provenance()` returns the block every result file must carry, so any
number can be traced to the machine, software, model weights and code that
produced it:

  * machine_id (EIH_MACHINE_ID), GPU model / driver / VRAM / power limits
  * Python, torch and CUDA/cuDNN versions
  * Ollama version and the sha256 digest of every local model
  * git commit SHA, branch, and whether the working tree had uncommitted changes
  * carbon region / intensity and TDP settings in force

A field that cannot be read is recorded as None with no guess, so a missing
value is visible instead of silently filled in.
"""

from __future__ import annotations

import datetime as _dt
import json
import platform
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import PROJECT_ROOT, settings


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10, check=True
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def git_info() -> Dict[str, Any]:
    # "dirty" means tracked files differ from the commit. Untracked files are
    # excluded: a run's own freshly written result files must not mark the
    # code that produced them as uncommitted.
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "sha": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status) if status is not None else None,
    }


def gpu_info(device_index: int = 0) -> Dict[str, Any]:
    info: Dict[str, Any] = {"name": None, "driver": None, "vram_total_mib": None,
                            "power_default_limit_w": None, "power_max_limit_w": None,
                            "compute_capability": None}
    try:
        import pynvml  # type: ignore[import]

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(device_index)
        name = pynvml.nvmlDeviceGetName(h)
        info["name"] = name.decode() if isinstance(name, bytes) else name
        drv = pynvml.nvmlSystemGetDriverVersion()
        info["driver"] = drv.decode() if isinstance(drv, bytes) else drv
        info["vram_total_mib"] = pynvml.nvmlDeviceGetMemoryInfo(h).total >> 20
        try:
            info["power_default_limit_w"] = pynvml.nvmlDeviceGetPowerManagementDefaultLimit(h) / 1000
            info["power_max_limit_w"] = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(h)[1] / 1000
        except Exception:  # noqa: BLE001
            pass
        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(h)
        info["compute_capability"] = f"{major}.{minor}"
    except Exception:  # noqa: BLE001
        pass
    return info


def torch_info() -> Dict[str, Any]:
    try:
        import torch

        return {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "cudnn": torch.backends.cudnn.version(),
            "cuda_available": torch.cuda.is_available(),
        }
    except Exception:  # noqa: BLE001
        return {"torch": None, "cuda": None, "cudnn": None, "cuda_available": None}


def ollama_info(base_url: Optional[str] = None, timeout: float = 5.0) -> Dict[str, Any]:
    base = (base_url or settings.secrets.local_model_base_url or "http://localhost:11434").rstrip("/")
    result: Dict[str, Any] = {"base_url": base, "version": None, "models": {}}
    try:
        with urllib.request.urlopen(f"{base}/api/version", timeout=timeout) as r:
            result["version"] = json.load(r).get("version")
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as r:
            for m in json.load(r).get("models", []):
                d = m.get("details", {})
                result["models"][m["name"]] = {
                    "digest": m.get("digest"),
                    "size_bytes": m.get("size"),
                    "parameter_size": d.get("parameter_size"),
                    "quantization": d.get("quantization_level"),
                }
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def collect_provenance(include_ollama: bool = True) -> Dict[str, Any]:
    sus = settings.sustainability
    return {
        "recorded_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "machine_id": settings.machine_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "gpu": gpu_info(),
        "torch": torch_info(),
        "ollama": ollama_info() if include_ollama else None,
        "git": git_info(),
        "sustainability_config": {
            "carbon_region": sus.carbon_region,
            "carbon_intensity_gco2_per_kwh": sus.carbon_intensity_gco2_per_kwh,
            "cpu_tdp_watts": sus.cpu_tdp_watts,
            "gpu_tdp_watts": sus.gpu_tdp_watts,
        },
    }


def write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
