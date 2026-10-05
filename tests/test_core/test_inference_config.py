"""configs/inference.yaml is the single source of truth for generation settings (Systems A-E + routing tiers)."""

from __future__ import annotations

import pytest

from core.inference import inference_config, load_inference_config


def test_every_consumer_reads_the_one_config():
    from core.config import settings
    from experiments.m5.manifest import ExperimentManifest
    from generation.providers.factory import local_model_options
    from generation.providers.ollama import DEFAULT_NUM_CTX, DEFAULT_SEED, OllamaProvider

    c = inference_config()
    assert settings.model.default_model_id == c.fixed_model
    assert settings.model.max_tokens == c.max_output_tokens
    assert settings.model.temperature == c.temperature
    assert (DEFAULT_NUM_CTX, DEFAULT_SEED) == (c.num_ctx, c.seed)
    assert OllamaProvider(base_url="http://x").keep_alive == c.keep_alive
    fv = ExperimentManifest.create_default().frozen_variables
    assert (fv.llm_model_id, fv.llm_num_ctx, fv.llm_num_gpu, fv.max_output_tokens) == (
        c.fixed_model, c.num_ctx, c.num_gpu, c.max_output_tokens)
    # every model a system or routing tier can call gets identical options
    opts = local_model_options()
    assert set(opts) == {c.fixed_model, c.fallback_model, *c.routing_ladder.values()}
    assert all(o == {"num_gpu": c.num_gpu} for o in opts.values())


def test_current_values_are_the_decided_ones():
    c = inference_config()
    assert (c.num_ctx, c.num_gpu, c.max_output_tokens, c.temperature, c.seed) == (12288, 999, 2048, 0.0, 42)
    assert c.routing_ladder == {"small": "qwen2.5-coder:1.5b", "medium": "qwen2.5-coder:3b",
                                "large": "qwen2.5-coder:7b"}


def test_a_config_missing_a_required_option_is_rejected(tmp_path):
    p = tmp_path / "inference.yaml"
    p.write_text("provider: ollama\nfixed_model: m\nfallback_model: m\nrouting_ladder: {small: m}\n"
                 "options: {num_ctx: 4096, temperature: 0.0, seed: 42}\n")
    with pytest.raises(ValueError, match="num_gpu"):
        load_inference_config(p)
