import os
import gradio as gr
import requests
from PIL import Image
import base64
import io
import imageio
import json
import socket
url = "http://localhost:8080/completion"
headers = {"Content-Type": "application/json"}
running = False
str = "■"
def run(frame, prompt):
    global running
    global str
    if running:
        return
    running = True
    imageio.imsave('temp.png', frame)
    with open("temp.png", 'rb') as file:
        encoded_string = base64.b64encode(file.read()).decode('utf-8')
    image_data = [{"data": encoded_string, "id": 12}]
    data = {"prompt": "USER:[img-12]" + prompt +".\nASSISTANT:", "n_predict": 128, "image_data": image_data, "stream": True}
    response = requests.post(url, headers=headers, json=data, stream=True)
    with open("output.txt", "a") as write_file:
        write_file.write("---"*10 + "\n\n")
    for chunk in response.iter_content(chunk_size=128):
        with open("output.txt", "a") as write_file:
            content = chunk.decode().strip().split('\n\n')[0]
            try:
                content_split = content.split('data: ')
                if len(content_split) > 1:
                    content_json = json.loads(content_split[1])
                    write_file.write(content_json["content"])
                    print(content_json["content"], end='', flush=True)
                    str = str + content_json["content"]
                    yield str
                write_file.flush()  # Save the file after every chunk
            except json.JSONDecodeError:
                print("JSONDecodeError: Expecting property name enclosed in double quotes")
    running = False
    str = str + "\n\n■"

css = """
#component-5 {
  position: fixed;
  top:0;
  left:0;
  bottom:0;
  right:0;
  padding: 0 !important;
  border-radius: 0 !important;
}
#component-1 {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 400px !important;
  width: auto !important;
  padding: 0;
  background: none !important;
}
#component-10 {
  z-index:1000;
  position: fixed;
  top: 0px;
  right: 0px;
  bottom: 0px;
  border-radius: 0 !important;
  background: none !important;
  border: none !important;
  padding: 0 !important;
  height: 100% !important;
  box-sizing: border-box !important;
  width: 400px !important;
}
#component-10 .form {
  background: none !important;
  border: none !important;
  height: 100% !important;
  box-sizing: border-box !important;
  border-radius: 0 !important;
}
#component-10 .form .container {
  height: 100%;
}
#component-2 {
  background: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  border: none !important;
  height: 100% !important;
  box-sizing: border-box !important;
}
.generating {
  border: none !important;
}
.upload-container {
  width: 100%;
  height: 100%;
}
button {
  display: none !important;
}
textarea {
  background: rgba(0,0,0,0.2) !important;
  color: white !important;
  font-family: monospace !important;
  font-size: 16px !important;
  -webkit-text-fill-color: white !important;
  border: none !important;
  padding: 30px !important;
  height: 100% !important;
  box-sizing: border-box !important;
  border-radius: 0 !important;
}
.progress-text {
  background: none !important;;
  border: none !important;
  color: white !important;
}

video {
  height: auto !important;
}
#component-9 {
  display: none;
}
[data-testid="block-label"] {
  display: none !important;
}
#component-2 [data-testid="block-info"] {
  display: none;
}
[data-testid="block-info"] {
  padding: 10px !important;
  background: rgba(0,0,0,0.2) !important;
  display: block;
  color: white !important;
  margin: 0 !important;
}
"""





from __future__ import annotations

import torch
from PIL import Image
from einops import rearrange
from torchvision.transforms.v2 import (
    Compose,
    Resize,
    InterpolationMode,
    ToImage,
    ToDtype,
    Normalize,
)

from transformers import CodeGenTokenizerFast as Tokenizer
from accelerate import init_empty_weights, load_checkpoint_and_dispatch
import re

import math
from typing import Optional

from transformers import PretrainedConfig


import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union

import torch
import torch.nn as nn
from einops import rearrange, repeat
from transformers import PretrainedConfig, PreTrainedModel
from transformers.activations import ACT2FN
from transformers.modeling_outputs import CausalLMOutputWithPast

pad_input, unpad_input = None, None
FlashRotaryEmbedding = None
FlashSelfAttention, FlashCrossAttention = None, None
FusedDense = None

if torch.cuda.is_available():
    DEVICE = "cuda"
    DTYPE = torch.float16
elif torch.backends.mps.is_available():
    DEVICE = "mps"
    DTYPE = torch.float32
else:
    DEVICE = "cpu"
    DTYPE = torch.float32


class PhiConfig(PretrainedConfig):
    """Phi configuration."""

    model_type = "phi-msft"
    attribute_map = {
        "max_position_embeddings": "n_positions",
        "hidden_size": "n_embd",
        "num_attention_heads": "n_head",
        "num_hidden_layers": "n_layer",
    }

    def __init__(
        self,
        vocab_size: int = 50304,
        n_positions: int = 2048,
        n_embd: int = 1024,
        n_layer: int = 20,
        n_inner: Optional[int] = None,
        n_head: int = 16,
        n_head_kv: Optional[int] = None,
        rotary_dim: Optional[int] = 32,
        activation_function: Optional[str] = "gelu_new",
        flash_attn: bool = False,
        flash_rotary: bool = False,
        fused_dense: bool = False,
        attn_pdrop: float = 0.0,
        embd_pdrop: float = 0.0,
        resid_pdrop: float = 0.0,
        layer_norm_epsilon: float = 1e-5,
        initializer_range: float = 0.02,
        tie_word_embeddings: bool = False,
        pad_vocab_size_multiple: int = 64,
        gradient_checkpointing: bool = False,
        **kwargs,
    ) -> None:
        self.vocab_size = int(
            math.ceil(vocab_size / pad_vocab_size_multiple) * pad_vocab_size_multiple
        )
        self.n_positions = n_positions
        self.n_embd = n_embd
        self.n_layer = n_layer
        self.n_inner = n_inner
        self.n_head = n_head
        self.n_head_kv = n_head_kv
        self.rotary_dim = min(rotary_dim, n_embd // n_head)
        self.activation_function = activation_function
        self.flash_attn = flash_attn
        self.flash_rotary = flash_rotary
        self.fused_dense = fused_dense
        self.attn_pdrop = attn_pdrop
        self.embd_pdrop = embd_pdrop
        self.resid_pdrop = resid_pdrop
        self.layer_norm_epsilon = layer_norm_epsilon
        self.initializer_range = initializer_range
        self.gradient_checkpointing = gradient_checkpointing

        super().__init__(tie_word_embeddings=tie_word_embeddings, **kwargs)


@dataclass
class InferenceParams:
    """Inference parameters passed to model to efficiently calculate
    and store context during inference.
    Reference:
        https://github.com/Dao-AILab/flash-attention/blob/main/flash_attn/utils/generation.py.
    Args:
        max_seqlen: Maximum sequence length.
        max_batch_size: Maximum batch size.
        seqlen_offset: Sequence length offset.
        batch_size_offset: Batch size offset.
        key_value_memory_dict: Key value memory dictionary.
        lengths_per_sample: Lengths per sample.
    """

    max_seqlen: int = field(metadata={"help": "Maximum sequence length."})

    max_batch_size: int = field(metadata={"help": "Maximum batch size."})

    seqlen_offset: int = field(default=0, metadata={"help": "Sequence length offset."})

    batch_size_offset: int = field(default=0, metadata={"help": "Batch size offset."})

    key_value_memory_dict: Dict[str, Any] = field(
        default_factory=dict, metadata={"help": "Key value memory dictionary."}
    )

    lengths_per_sample: torch.Tensor = field(
        default=None, metadata={"help": "Lengths per sample."}
    )


class Embedding(nn.Module):
    """Token embedding with dropout."""

    def __init__(self, config: PretrainedConfig) -> None:
        super().__init__()

        self.wte = nn.Embedding(config.vocab_size, config.n_embd)
        self.drop = nn.Dropout(config.embd_pdrop)

    def forward(self, input_ids: torch.LongTensor) -> torch.FloatTensor:
        input_shape = input_ids.size()
        input_ids = input_ids.view(-1, input_shape[-1])

        hidden_states = self.wte(input_ids)
        hidden_states = self.drop(hidden_states)

        return hidden_states


# @torch.compile
def _apply_rotary_emb(
    x: torch.FloatTensor,
    cos: torch.FloatTensor,
    sin: torch.FloatTensor,
) -> torch.FloatTensor:
    _, seqlen, _, _ = x.shape
    _, rotary_dim = cos.shape
    rotary_dim *= 2

    x_rot = x[:, :, :, :rotary_dim]
    x_pass = x[:, :, :, rotary_dim:]

    x1, x2 = x_rot.chunk(2, dim=-1)
    c, s = rearrange(cos[:seqlen], "s d -> s 1 d"), rearrange(
        sin[:seqlen], "s d -> s 1 d"
    )
    x1, x2, c, s = [t.to(dtype=torch.float32) for t in [x1, x2, c, s]]

    x_rot = torch.cat([x1 * c - x2 * s, x1 * s + x2 * c], axis=-1).to(x.dtype)

    return torch.cat([x_rot, x_pass], axis=-1)


# @torch.compile
def _apply_rotary_emb_kv(
    kv: torch.FloatTensor,
    cos: torch.FloatTensor,
    sin: torch.FloatTensor,
    cos_k: Optional[torch.FloatTensor] = None,
    sin_k: Optional[torch.FloatTensor] = None,
) -> torch.FloatTensor:
    _, seqlen, _, _, _ = kv.shape
    _, rotary_dim = cos.shape
    rotary_dim *= 2

    k_rot = kv[:, :, 0, :, :rotary_dim]
    k_pass = kv[:, :, 0, :, rotary_dim:]

    k1, k2 = k_rot.chunk(2, dim=-1)
    c, s = rearrange(cos[:seqlen], "s d -> s 1 d"), rearrange(
        sin[:seqlen], "s d -> s 1 d"
    )
    k1, k2, c, s = [t.to(dtype=torch.float32) for t in [k1, k2, c, s]]

    k_rot = torch.cat([k1 * c - k2 * s, k1 * s + k2 * c], axis=-1).to(kv.dtype)

    return torch.cat(
        [
            torch.cat([k_rot, k_pass], axis=-1).unsqueeze(2),
            kv[:, :, 1:2, :, :],
        ],
        axis=2,
    )


# @torch.compile
def _apply_rotary_emb_qkv(
    qkv: torch.FloatTensor,
    cos: torch.FloatTensor,
    sin: torch.FloatTensor,
    cos_k: Optional[torch.FloatTensor] = None,
    sin_k: Optional[torch.FloatTensor] = None,
) -> torch.FloatTensor:
    _, seqlen, _, _, _ = qkv.shape
    _, rotary_dim = cos.shape
    rotary_dim *= 2

    q_rot = qkv[:, :, 0, :, :rotary_dim]
    q_pass = qkv[:, :, 0, :, rotary_dim:]

    k_rot = qkv[:, :, 1, :, :rotary_dim]
    k_pass = qkv[:, :, 1, :, rotary_dim:]

    q1, q2 = q_rot.chunk(2, dim=-1)
    k1, k2 = k_rot.chunk(2, dim=-1)
    c, s = rearrange(cos[:seqlen], "s d -> s 1 d"), rearrange(
        sin[:seqlen], "s d -> s 1 d"
    )
    q1, q2, k1, k2, c, s = [t.to(dtype=torch.float32) for t in [q1, q2, k1, k2, c, s]]

    q_rot = torch.cat([q1 * c - q2 * s, q1 * s + q2 * c], axis=-1).to(qkv.dtype)
    k_rot = torch.cat([k1 * c - k2 * s, k1 * s + k2 * c], axis=-1).to(qkv.dtype)

    return torch.cat(
        [
            torch.cat([q_rot, q_pass], axis=-1).unsqueeze(2),
            torch.cat([k_rot, k_pass], axis=-1).unsqueeze(2),
            qkv[:, :, 2:3, :, :],
        ],
        axis=2,
    )


class RotaryEmbedding(nn.Module):
    """Rotary positional embedding (RoPE).
    Reference:
        RoFormer: Enhanced Transformer with Rotary Position Embedding.
        https://arxiv.org/pdf/2104.09864.pdf.
    """

    def __init__(
        self,
        dim: int,
        base: int = 10000,
        scale_base: Optional[float] = None,
        pos_idx_in_fp32: bool = True,
        max_position_embeddings: int = 2048,
        device: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__()

        if scale_base is not None:
            raise NotImplementedError

        self.dim = dim
        self.base = float(base)
        self.scale_base = scale_base
        self.pos_idx_in_fp32 = pos_idx_in_fp32
        self.max_position_embeddings = max_position_embeddings
        self.device = device

        # Generate and save the inverse frequency buffer (non-trainable)
        inv_freq = self._compute_inv_freq(device)
        self.register_buffer("inv_freq", inv_freq, persistent=False)

        # Generate and save the scale buffer (non-trainable)
        scale = (
            (torch.arange(0, dim, 2, device=device, dtype=torch.float32) + 0.4 * dim)
            / (1.4 * dim)
            if scale_base is not None
            else None
        )
        self.register_buffer("scale", scale, persistent=False)

        # Initialize cached attributes since ONNX can't rely on dynamic initialization
        self._update_cos_sin_cache(
            max_position_embeddings, device=device, dtype=torch.float32
        )

    def _compute_inv_freq(self, device: Optional[str] = None) -> torch.FloatTensor:
        return 1.0 / (
            self.base
            ** (
                torch.arange(0, self.dim, 2, device=device, dtype=torch.float32)
                / self.dim
            )
        )

    def _update_cos_sin_cache(
        self,
        seqlen: int,
        device: Optional[str] = None,
        dtype: Optional[torch.dtype] = None,
    ) -> None:
        self._seq_len_cached = seqlen

        # fp32 is preferred since the output of `torch.arange` can be quite large
        # and bf16 would lose a lot of precision
        if self.pos_idx_in_fp32:
            t = torch.arange(seqlen, device=device, dtype=torch.float32)
            if self.inv_freq.dtype != torch.float32:
                inv_freq = self._compute_inv_freq(device=device)
            else:
                inv_freq = self.inv_freq
        else:
            t = torch.arange(seqlen, device=device, dtype=self.inv_freq.dtype)
            inv_freq = self.inv_freq

        # `torch.outer` is preferred since `torch.einsum` converts from fp32 to fp16 if used with AMP
        freqs = torch.outer(t, inv_freq)
        if self.scale is None:
            self._cos_cached = torch.cos(freqs).to(dtype)
            self._sin_cached = torch.sin(freqs).to(dtype)
        else:
            power = (
                torch.arange(seqlen, dtype=self.scale.dtype, device=self.scale.device)
                - seqlen // 2
            ) / self.scale_base
            scale = self.scale.to(device=power.device) ** rearrange(power, "s -> s 1")

            # Force the scale multiplication to happen in fp32
            self._cos_cached = (torch.cos(freqs) * scale).to(dtype)
            self._sin_cached = (torch.sin(freqs) * scale).to(dtype)
            self._cos_k_cached = (torch.cos(freqs) / scale).to(dtype)
            self._sin_k_cached = (torch.sin(freqs) / scale).to(dtype)

    def forward(
        self,
        qkv: torch.Tensor,
        kv: Optional[torch.Tensor] = None,
        seqlen_offset: int = 0,
        **kwargs,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        if (
            self._seq_len_cached < qkv.shape[1] + seqlen_offset
            or self._cos_cached.device != qkv.device
            or self._cos_cached.dtype != qkv.dtype
            or (self.training and self._cos_cached.is_inference())
        ):
            self._update_cos_sin_cache(
                qkv.shape[1] + seqlen_offset, device=qkv.device, dtype=qkv.dtype
            )

        if kv is None:
            return _apply_rotary_emb_qkv(
                qkv,
                self._cos_cached[seqlen_offset:],
                self._sin_cached[seqlen_offset:],
            )
        else:
            q = _apply_rotary_emb(
                qkv,
                self._cos_cached[seqlen_offset:],
                self._sin_cached[seqlen_offset:],
            )
            kv = _apply_rotary_emb_kv(
                kv,
                self._cos_cached[seqlen_offset:],
                self._sin_cached[seqlen_offset:],
            )

            return q, kv


class MLP(nn.Module):
    """Multi-Layer Perceptron.
    Reference:
        Attention Is All You Need.
        https://arxiv.org/pdf/1706.03762.pdf.
    """

    def __init__(
        self,
        config: PretrainedConfig,
        n_inner: Optional[int] = None,
        act_fn: Optional[str] = None,
    ) -> None:
        super().__init__()

        act_fn = config.activation_function if act_fn is None else act_fn

        n_inner = getattr(config, "n_inner", None) if n_inner is None else n_inner
        n_inner = n_inner if n_inner is not None else 4 * config.n_embd

        self.fc1 = nn.Linear(config.n_embd, n_inner)
        self.fc2 = nn.Linear(n_inner, config.n_embd)
        self.act = ACT2FN[act_fn]

    def forward(self, hidden_states: torch.FloatTensor) -> torch.FloatTensor:
        hidden_states = self.fc1(hidden_states)
        hidden_states = self.act(hidden_states)
        hidden_states = self.fc2(hidden_states)

        return hidden_states


class SelfAttention(nn.Module):
    """Self-attention layer (compatible with PyTorch).
    Reference:
        https://github.com/Dao-AILab/flash-attention/blob/main/flash_attn/modules/mha.py.
    """

    def __init__(
        self,
        causal: bool = True,
        softmax_scale: Optional[float] = None,
        attention_dropout: float = 0.0,
    ) -> None:
        super().__init__()

        self.causal = causal
        self.softmax_scale = softmax_scale
        self.drop = nn.Dropout(attention_dropout)

    @torch.autocast("cpu", enabled=False)
    @torch.autocast("cuda", enabled=False)
    def forward(
        self,
        qkv: torch.FloatTensor,
        causal: bool = None,
        key_padding_mask: Optional[torch.BoolTensor] = None,
        **kwargs,
    ) -> torch.FloatTensor:
        batch_size, seqlen = qkv.shape[0], qkv.shape[1]
        q, k, v = qkv.unbind(dim=2)

        q = q.to(torch.float32)
        k = k.to(torch.float32)

        causal = self.causal if causal is None else causal
        softmax_scale = self.softmax_scale or 1.0 / math.sqrt(q.shape[-1])

        # Autocast is manually disabled to avoid `torch.einsum` performing the operation
        # using float16, which might lead to overflow
        scores = torch.einsum("bthd,bshd->bhts", q, k * softmax_scale)

        if key_padding_mask is not None:
            padding_mask = torch.full(
                (batch_size, seqlen), -10000.0, dtype=scores.dtype, device=scores.device
            )
            padding_mask.masked_fill_(key_padding_mask, 0.0)

            scores = scores + rearrange(padding_mask, "b s -> b 1 1 s")

        if causal:
            causal_mask = torch.triu(
                torch.full((seqlen, seqlen), -10000.0, device=scores.device), 1
            )
            scores = scores + causal_mask.to(dtype=scores.dtype)

        attention = torch.softmax(scores, dim=-1).to(v.dtype)
        attention = self.drop(attention)

        output = torch.einsum("bhts,bshd->bthd", attention, v)

        return output


class CrossAttention(nn.Module):
    """Cross-attention layer (compatible with PyTorch).
    Reference:
        https://github.com/Dao-AILab/flash-attention/blob/main/flash_attn/modules/mha.py.
    """

    def __init__(
        self,
        causal: bool = True,
        softmax_scale: Optional[float] = None,
        attention_dropout: float = 0.0,
    ) -> None:
        super().__init__()

        self.causal = causal
        self.softmax_scale = softmax_scale
        self.drop = nn.Dropout(attention_dropout)

    @torch.autocast("cpu", enabled=False)
    @torch.autocast("cuda", enabled=False)
    def forward(
        self,
        q: torch.FloatTensor,
        kv: torch.FloatTensor,
        causal: bool = None,
        key_padding_mask: Optional[torch.BoolTensor] = None,
        **kwargs,
    ) -> torch.FloatTensor:
        batch_size, seqlen_q = q.shape[0], q.shape[1]
        seqlen_k = kv.shape[1]

        if kv.shape[3] != q.shape[2]:
            kv = repeat(kv, "... hkv d -> ... (hkv g) d", g=q.shape[2] // kv.shape[3])
        k, v = kv.unbind(dim=2)

        q = q.to(torch.float32)
        k = k.to(torch.float32)

        causal = self.causal if causal is None else causal
        softmax_scale = self.softmax_scale or 1.0 / math.sqrt(q.shape[-1])

        # Autocast is manually disabled to avoid `torch.einsum` performing the operation
        # using float16, which might lead to overflow
        scores = torch.einsum("bthd,bshd->bhts", q, k * softmax_scale)

        if key_padding_mask is not None:
            padding_mask = torch.full(
                (batch_size, seqlen_k),
                -10000.0,
                dtype=scores.dtype,
                device=scores.device,
            )
            padding_mask.masked_fill_(key_padding_mask, 0.0)

            scores = scores + rearrange(padding_mask, "b s -> b 1 1 s")

        if causal:
            rows = rearrange(
                torch.arange(seqlen_q, device=q.device, dtype=torch.long), "s -> s 1"
            )
            cols = torch.arange(seqlen_k, device=k.device, dtype=torch.long)
            causal_mask = cols > rows + seqlen_k - seqlen_q

            scores = scores.masked_fill(causal_mask, -10000.0)

        attention = torch.softmax(scores, dim=-1).to(v.dtype)
        attention = self.drop(attention)

        output = torch.einsum("bhts,bshd->bthd", attention, v)

        return output


def _find_mha_dims(
    config: PretrainedConfig,
    n_head: Optional[int] = None,
    n_head_kv: Optional[int] = None,
    head_dim: Optional[int] = None,
) -> Tuple[int, int]:
    if n_head is None and head_dim is None:
        head_dim = config.n_embd // config.n_head
        n_head = config.n_head
    elif n_head is None or head_dim is None:
        raise ValueError("`n_head` and `head_dim` must be both specified or `None`.")

    if n_head_kv is None:
        n_head_kv = getattr(config, "n_head_kv", None) or n_head

    return n_head, n_head_kv, head_dim


def _update_kv_cache(
    kv: torch.FloatTensor, inference_params: InferenceParams, layer_idx: int
) -> torch.FloatTensor:
    num_heads, head_dim = kv.shape[-2:]

    if layer_idx not in inference_params.key_value_memory_dict:
        inference_params.key_value_memory_dict[layer_idx] = torch.empty(
            inference_params.max_batch_size,
            inference_params.max_seqlen,
            2,
            num_heads,
            head_dim,
            dtype=kv.dtype,
            device=kv.device,
        )

    batch_start = inference_params.batch_size_offset
    batch_end = batch_start + kv.shape[0]

    sequence_start = inference_params.seqlen_offset
    sequence_end = sequence_start + kv.shape[1]

    # When the current sequence length is equal to or larger than the maximum sequence length,
    # we need to concatenate the current `kv` with the cached `kv` to expand its length
    if sequence_end >= inference_params.max_seqlen:
        inference_params.key_value_memory_dict[layer_idx] = torch.concatenate(
            (inference_params.key_value_memory_dict[layer_idx], kv), dim=1
        )

    inference_params.key_value_memory_dict[layer_idx][
        batch_start:batch_end, sequence_start:sequence_end, ...
    ] = kv
    kv = inference_params.key_value_memory_dict[layer_idx][
        batch_start:batch_end, :sequence_end, ...
    ]

    return kv


class MHA(nn.Module):
    """Multi-head attention layer."""

    def __init__(
        self,
        config: PretrainedConfig,
        dtype: Optional[torch.dtype] = None,
        device: Optional[str] = None,
        rotary_dim: Optional[int] = None,
        rotary_base: float = 10000.0,
        rotary_scale_base: Optional[float] = None,
        n_head: Optional[int] = None,
        n_head_kv: Optional[int] = None,
        head_dim: Optional[int] = None,
        bias: bool = True,
        causal: bool = True,
        softmax_scale: Optional[float] = None,
        layer_idx: Optional[int] = None,
        return_residual: bool = False,
        checkpointing: bool = False,
    ) -> None:
        super().__init__()

        # Rotary embedding
        self.rotary_dim = (
            rotary_dim if rotary_dim is not None else getattr(config, "rotary_dim", 0)
        )

        if self.rotary_dim > 0:
            self.rotary_emb = RotaryEmbedding(
                self.rotary_dim,
                base=rotary_base,
                scale_base=rotary_scale_base,
                device=device,
                max_position_embeddings=config.n_positions,
            )

        # MLP
        self.n_head, self.n_head_kv, self.head_dim = _find_mha_dims(
            config, n_head=n_head, n_head_kv=n_head_kv, head_dim=head_dim
        )
        op_size = self.head_dim * (self.n_head + 2 * self.n_head_kv)
        hidden_size = config.n_embd

        linear_cls = FusedDense if config.fused_dense else nn.Linear
        if linear_cls is None:
            linear_cls = nn.Linear

        self.Wqkv = linear_cls(
            hidden_size, op_size, bias=bias, device=device, dtype=dtype
        )
        self.out_proj = linear_cls(
            hidden_size, hidden_size, bias=bias, device=device, dtype=dtype
        )

        # Attention
        self.inner_attn = SelfAttention(
            causal=causal,
            softmax_scale=softmax_scale,
            attention_dropout=config.attn_pdrop,
        )
        self.inner_cross_attn = CrossAttention(
            causal=causal,
            softmax_scale=softmax_scale,
            attention_dropout=config.attn_pdrop,
        )

        self.layer_idx = layer_idx
        self.return_residual = return_residual
        self.checkpointing = checkpointing

    def _forward_self_attn(
        self, x: torch.FloatTensor, key_padding_mask: Optional[torch.BoolTensor]
    ) -> torch.FloatTensor:
        qkv = self.Wqkv(x)
        qkv = rearrange(
            qkv, "... (three h d) -> ... three h d", three=3, d=self.head_dim
        )

        if self.rotary_dim > 0:
            qkv = self.rotary_emb(qkv)

        if self.checkpointing:
            return torch.utils.checkpoint.checkpoint(
                self.inner_attn, qkv, key_padding_mask=key_padding_mask
            )

        return self.inner_attn(qkv, key_padding_mask=key_padding_mask)

    def _forward_cross_attn(
        self,
        x: torch.FloatTensor,
        past_key_values: Optional[InferenceParams],
        key_padding_mask: Optional[torch.BoolTensor],
    ) -> torch.FloatTensor:
        batch_size = x.shape[0]

        qkv = self.Wqkv(x)

        q = qkv[..., : self.n_head * self.head_dim]
        q = rearrange(q, "... (h d) -> ... h d", d=self.head_dim)

        kv = qkv[..., self.n_head * self.head_dim :]
        kv = rearrange(kv, "... (two hkv d) -> ... two hkv d", two=2, d=self.head_dim)

        seqlen_offset = (
            past_key_values.seqlen_offset if past_key_values is not None else 0
        )
        causal = None if seqlen_offset == 0 else False
        if self.rotary_dim > 0:
            q, kv = self.rotary_emb(q, kv=kv, seqlen_offset=seqlen_offset)

        if past_key_values is not None:
            kv = _update_kv_cache(kv, past_key_values, self.layer_idx)

        if self.checkpointing:
            return torch.utils.checkpoint.checkpoint(
                self.inner_cross_attn,
                q,
                kv,
                key_padding_mask=key_padding_mask,
                causal=causal,
            )

        return self.inner_cross_attn(
            q, kv, key_padding_mask=key_padding_mask, causal=causal
        )

    def forward(
        self,
        x: torch.FloatTensor,
        past_key_values: Optional[InferenceParams] = None,
        attention_mask: Optional[Union[torch.LongTensor, torch.BoolTensor]] = None,
        **kwargs,
    ) -> Tuple[torch.FloatTensor, torch.FloatTensor]:
        if attention_mask is not None:
            attention_mask = attention_mask.bool()
        else:
            attention_mask = None

        # MHA
        if self.n_head == self.n_head_kv:
            if past_key_values is None:
                # If `past_key_values` are not supplied, we run self-attention
                attn_output = self._forward_self_attn(x, attention_mask)
            else:
                # If `past_key_values` are supplied, it means that we might have cached values and
                # could take advantage of cross-attention
                attn_output = self._forward_cross_attn(
                    x, past_key_values, attention_mask
                )
        # MQA / GQA
        else:
            # Regardless of `past_key_values` being supplied or not, it always use cross-attention
            # because `q` and `kv` lengths might be different
            attn_output = self._forward_cross_attn(x, past_key_values, attention_mask)

        output = rearrange(attn_output, "... h d -> ... (h d)")
        output = self.out_proj(output)

        return output if not self.return_residual else (output, x)


class ParallelBlock(nn.Module):
    """Parallel block.
    This block applies parallel mixer and MLP layers to the input (used in GPT-J and CodeGen).
    """

    def __init__(
        self,
        config: PretrainedConfig,
        block_idx: Optional[int] = None,
    ) -> None:
        super().__init__()

        self.ln = nn.LayerNorm(config.n_embd, eps=config.layer_norm_epsilon)
        self.resid_dropout = nn.Dropout(config.resid_pdrop)
        self.block_idx = block_idx

        self.mixer = MHA(config, layer_idx=block_idx)
        self.mlp = MLP(config)

    def forward(
        self,
        hidden_states: torch.FloatTensor,
        past_key_values: Optional[Union[torch.FloatTensor, InferenceParams]] = None,
        attention_mask: Optional[torch.BoolTensor] = None,
        **kwargs,
    ) -> torch.FloatTensor:
        residual = hidden_states
        hidden_states = self.ln(hidden_states)

        attn_outputs = self.mixer(
            hidden_states,
            past_key_values=past_key_values,
            attention_mask=attention_mask,
        )
        if isinstance(attn_outputs, tuple):
            attn_outputs = attn_outputs[0]

        attn_outputs = self.resid_dropout(attn_outputs)
        feed_forward_hidden_states = self.resid_dropout(self.mlp(hidden_states))

        hidden_states = attn_outputs + feed_forward_hidden_states + residual

        return hidden_states


class CausalLMHead(nn.Module):
    """Causal Language Modeling head.
    Reference:
        Improving Language Understanding by Generative Pre-Training.
        https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf.
    """

    def __init__(self, config: PretrainedConfig) -> None:
        super().__init__()

        self.ln = nn.LayerNorm(config.n_embd, eps=config.layer_norm_epsilon)
        self.linear = nn.Linear(config.n_embd, config.vocab_size)

    def forward(self, hidden_states: torch.FloatTensor) -> torch.FloatTensor:
        hidden_states = self.ln(hidden_states)
        logits = self.linear(hidden_states).to(torch.float32)

        return logits


class CausalLMLoss(nn.Module):
    """Causal Language Modeling loss.
    Reference:
        Improving Language Understanding by Generative Pre-Training.
        https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf.
    """

    def __init__(self, shift_labels: bool = True) -> None:
        super().__init__()

        self.shift_labels = shift_labels
        self.loss_fct = nn.CrossEntropyLoss()

    def forward(
        self, logits: torch.FloatTensor, labels: torch.LongTensor
    ) -> torch.FloatTensor:
        if self.shift_labels:
            logits = logits[..., :-1, :].contiguous()
            labels = labels[..., 1:].contiguous()

        loss = self.loss_fct(logits.view(-1, logits.size(-1)), labels.view(-1))

        return loss


class PhiPreTrainedModel(PreTrainedModel):
    """Phi pre-trained model."""

    config_class = PhiConfig
    base_model_prefix = "transformer"
    supports_gradient_checkpointing = False
    _no_split_modules = ["ParallelBlock"]

    def __init__(self, *inputs, **kwargs) -> None:
        super().__init__(*inputs, **kwargs)

    def prepare_inputs_for_generation(
        self,
        input_ids: torch.LongTensor = None,
        inputs_embeds: torch.FloatTensor = None,
        past_key_values: Optional[Union[torch.FloatTensor, InferenceParams]] = None,
        attention_mask: Optional[Union[torch.LongTensor, torch.BoolTensor]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if inputs_embeds is not None:
            max_batch_size = inputs_embeds.shape[0]
            seqlen_offset = inputs_embeds.shape[1] + input_ids.shape[1] - 2
        elif input_ids is not None:
            max_batch_size = input_ids.shape[0]
            seqlen_offset = input_ids.shape[1] - 1
        else:
            raise ValueError(
                "You have to specify either `input_ids` or `inputs_embeds`."
            )

        args = {}

        if past_key_values is None or not (
            isinstance(past_key_values, InferenceParams)
        ):
            past_key_values = InferenceParams(
                max_seqlen=self.config.n_positions,
                max_batch_size=max_batch_size,
                seqlen_offset=0,
                batch_size_offset=0,
                key_value_memory_dict={},
                lengths_per_sample=None,
            )
            if inputs_embeds is not None:
                args = {"inputs_embeds": inputs_embeds}
            elif input_ids is not None:
                args = {"input_ids": input_ids}
            else:
                raise ValueError(
                    "You have to specify either `input_ids` or `inputs_embeds`."
                )
        else:
            # Assume that `past_key_values` has cached all tokens up to the last token in `input_ids`
            past_key_values.seqlen_offset = seqlen_offset
            input_ids = input_ids[:, -1].unsqueeze(-1)
            args = {"input_ids": input_ids}

        return {
            **args,
            "past_key_values": past_key_values,
            "attention_mask": attention_mask,
        }


class PhiModel(PhiPreTrainedModel):
    """Phi model."""

    _keys_to_ignore_on_load_missing = [""]
    _keys_to_ignore_on_load_unexpected = [r"h\.\d+\.mlp.(fc_in|fc_out)\.(weight|bias)"]

    def __init__(self, config: PhiConfig) -> None:
        super().__init__(config)

        self.embd = Embedding(config)
        self.h = nn.ModuleList(
            [ParallelBlock(config, block_idx=i) for i in range(config.n_layer)]
        )
        self.gradient_checkpointing = config.gradient_checkpointing
        self.post_init()

    def get_input_embeddings(self) -> nn.Embedding:
        return self.embd.wte

    def set_input_embeddings(self, new_embeddings: nn.Embedding) -> None:
        self.embd.wte = new_embeddings

    def forward(
        self,
        input_ids: torch.LongTensor = None,
        inputs_embeds: torch.FloatTensor = None,
        past_key_values: Optional[Union[torch.FloatTensor, InferenceParams]] = None,
        attention_mask: Optional[torch.BoolTensor] = None,
    ) -> torch.FloatTensor:
        if input_ids is not None and inputs_embeds is not None:
            raise ValueError(
                "You cannot specify both `input_ids` and `inputs_embeds` at the same time."
            )
        elif input_ids is None and inputs_embeds is None:
            raise ValueError(
                "You have to specify either `input_ids` or `inputs_embeds`."
            )
        elif input_ids is not None:
            hidden_states = self.embd(input_ids)
        else:
            hidden_states = inputs_embeds

        for layer in self.h:
            if self.gradient_checkpointing:
                hidden_states = torch.utils.checkpoint.checkpoint(
                    layer.__call__,
                    hidden_states,
                    past_key_values,
                    attention_mask,
                    use_reentrant=True,
                )
            else:
                hidden_states = layer(
                    hidden_states,
                    past_key_values=past_key_values,
                    attention_mask=attention_mask,
                )

        return hidden_states


class PhiForCausalLM(PhiPreTrainedModel):
    """Phi for Causal Language Modeling."""

    _keys_to_ignore_on_load_missing = [""]
    _keys_to_ignore_on_load_unexpected = [
        r"transformer\.h\.\d+\.mlp.(fc_in|fc_out)\.(weight|bias)"
    ]

    def __init__(self, config: PhiConfig) -> None:
        super().__init__(config)

        self.transformer = PhiModel(config)
        self.lm_head = CausalLMHead(config)
        self.loss = CausalLMLoss()

        self.post_init()

    def get_output_embeddings(self) -> nn.Linear:
        return self.lm_head.linear

    def set_output_embeddings(self, new_embeddings: nn.Linear) -> None:
        self.lm_head.linear = new_embeddings

    def forward(
        self,
        input_ids: torch.LongTensor = None,
        inputs_embeds: torch.FloatTensor = None,
        past_key_values: Optional[Union[torch.FloatTensor, InferenceParams]] = None,
        attention_mask: Optional[torch.BoolTensor] = None,
        labels: Optional[torch.LongTensor] = None,
        **kwargs,
    ) -> CausalLMOutputWithPast:
        hidden_states = self.transformer(
            input_ids,
            inputs_embeds,
            past_key_values=past_key_values,
            attention_mask=attention_mask,
        )
        lm_logits = self.lm_head(hidden_states)

        loss = None
        if labels is not None:
            loss = self.loss(lm_logits, labels)

        return CausalLMOutputWithPast(
            loss=loss, logits=lm_logits, past_key_values=past_key_values
        )


class VisionEncoder(nn.Module):
    def __init__(self, model_path: str = "model") -> None:
        super().__init__()
        self.model = torch.jit.load(f"{model_path}/vision.pt").to(DEVICE, dtype=DTYPE)
        self.preprocess = Compose(
            [
                Resize(size=(384, 384), interpolation=InterpolationMode.BICUBIC),
                ToImage(),
                ToDtype(torch.float32, scale=True),
                Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
            ]
        )

    def __call__(self, image: Image) -> torch.Tensor:
        with torch.no_grad():
            image_vec = self.preprocess(image.convert("RGB")).unsqueeze(0)
            image_vec = image_vec[:, :, :-6, :-6]
            image_vec = rearrange(
                image_vec, "b c (h p1) (w p2) -> b (h w) (c p1 p2)", p1=14, p2=14
            )

            image_vec = image_vec.to(DEVICE, dtype=DTYPE)
            return self.model(image_vec)


class TextModel(nn.Module):
    def __init__(self, model_path: str = "model") -> None:
        super().__init__()
        self.tokenizer = Tokenizer.from_pretrained(f"{model_path}/tokenizer")
        phi_config = PhiConfig.from_pretrained(f"{model_path}/text_model_cfg.json")

        with init_empty_weights():
            self.model = PhiForCausalLM(phi_config)

        self.model = load_checkpoint_and_dispatch(
            self.model,
            f"{model_path}/text_model.pt",
            device_map={"": DEVICE},
            dtype=DTYPE,
        )

        self.text_emb = self.model.get_input_embeddings()

    def input_embeds(self, prompt, image_embeds):
        embeds = []

        def _add_toks(toks):
            embeds.append(self.text_emb(toks))

        def _tokenize(txt):
            return self.tokenizer(
                txt, return_tensors="pt", add_special_tokens=False
            ).input_ids.to(self.model.device)

        # Add BOS token
        _add_toks(
            torch.tensor([[self.tokenizer.bos_token_id]], device=self.model.device)
        )

        if "<image>" not in prompt:
            embeds.append(self.text_emb(_tokenize(prompt)))
        else:
            assert prompt.count("<image>") == 1
            before, after = prompt.split("<image>")
            embeds.append(self.text_emb(_tokenize(f"{before}<image>")))
            embeds.append(image_embeds.to(self.model.device))
            embeds.append(self.text_emb(_tokenize(f"</image>{after}")))

        return torch.cat(embeds, dim=1)

    def generate(
        self, image_embeds, prompt, eos_text="Human:", max_new_tokens=128, **kwargs
    ):
        eos_tokens = self.tokenizer(eos_text, add_special_tokens=False)[0].ids

        generate_config = {
            "eos_token_id": eos_tokens,
            "bos_token_id": self.tokenizer.bos_token_id,
            "pad_token_id": self.tokenizer.eos_token_id,
            "max_new_tokens": max_new_tokens,
            **kwargs,
        }

        with torch.no_grad():
            inputs_embeds = self.input_embeds(prompt, image_embeds)
            output_ids = self.model.generate(
                inputs_embeds=inputs_embeds, **generate_config
            )

        return self.tokenizer.batch_decode(output_ids, skip_special_tokens=True)

    def answer_question(self, image_embeds, question, **kwargs):
        prompt = f"<image>\n\nQuestion: {question}\n\nAnswer:"
        answer = self.generate(
            image_embeds,
            prompt,
            eos_text="<END>",
            max_new_tokens=128,
            **kwargs,
        )[0]

        return re.sub("<$", "", re.sub("END$", "", answer)).strip()


##### GRADIO INTERFACE #####

import gradio as gr
from huggingface_hub import snapshot_download
from threading import Thread
from transformers import TextIteratorStreamer
import hashlib
import os

#model_path = snapshot_download("vikhyatk/moondream1")
model_path = os.path.abspath("moondream1")
print(f"model_path={model_path}")

vision_encoder = VisionEncoder(model_path).to(DEVICE, dtype=DTYPE)
text_model = TextModel(model_path).to(DEVICE, dtype=DTYPE)


def cached_vision_encoder(image):
    # Calculate checksum of the image
    image_hash = hashlib.sha256(image.tobytes()).hexdigest()

    # Check if `image_encoder_cache/{image_hash}.pt` exists, if so load and return it.
    # Otherwise, save the encoded image to `image_encoder_cache/{image_hash}.pt` and return it.
    cache_path = f"image_encoder_cache/{image_hash}.pt"
    if os.path.exists(cache_path):
        return torch.load(cache_path).to(DEVICE, dtype=DTYPE)
    else:
        image_vec = vision_encoder(image).to("cpu", dtype=torch.float16)
        os.makedirs("image_encoder_cache", exist_ok=True)
        torch.save(image_vec, cache_path)
        return image_vec.to(DEVICE, dtype=DTYPE)


def answer_question(image, question):
    yield "Encoding image..."

    streamer = TextIteratorStreamer(text_model.tokenizer, skip_special_tokens=True)
    generation_kwargs = dict(
        image_embeds=cached_vision_encoder(image), question=question, streamer=streamer
    )
    thread = Thread(target=text_model.answer_question, kwargs=generation_kwargs)
    thread.start()

    buffer = ""
    print(f"## answer_question {question}")
    for new_text in streamer:
        buffer += new_text
        if len(buffer) > 1:
            print(buffer, end='', flush=True)
            yield re.sub("<$", "", re.sub("END$", "", buffer))


demo = gr.Interface(
    answer_question,
    inputs=[
      gr.Image(sources=["webcam"], streaming=True),
      gr.Textbox(value="Describe a person in the image", label="Prompt")
    ],
    outputs=gr.Textbox(label="Output Box"),
    live=True,
    css=css
)
demo.dependencies[0]["show_progress"] = "minimal"
demo.launch()
