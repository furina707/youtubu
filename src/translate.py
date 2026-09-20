# -*- coding: utf-8 -*-
"""离线翻译（NLLB-200 经 HuggingFace transformers + PyTorch 本地推理）。

模型：facebook/nllb-200-distilled-600M
首次使用会自动下载 PyTorch 权重（约 1.2-2.5GB），之后完全离线。
一次可批量翻译多句，效率高于逐句调用。
"""

from __future__ import annotations


class LocalTranslator:
    """NLLB 离线翻译器（PyTorch CPU）。"""

    NLLB_REPO = "facebook/nllb-200-distilled-600M"

    def __init__(self, device: str = "cpu",
                 model_dir: str | None = None,
                 max_new_tokens: int = 160,
                 beam_size: int = 1):  # greedy：CPU 上快且质量已足够
        self.device = device
        self.model_dir = model_dir
        self.max_new_tokens = max_new_tokens
        self.beam_size = beam_size
        self._tok = None
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

        model_name = self.model_dir or self.NLLB_REPO
        self._tok = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        self._model.eval()
        self._model.to(self.device)

    def translate(self, text: str, source_iso: str, target_iso: str) -> str:
        """翻译单句。source_iso / target_iso 为 ISO 639-1 代码。"""
        outs = self.translate_batch([text], source_iso, target_iso)
        return outs[0] if outs else ""

    def translate_batch(self, texts: "list[str]", source_iso: str,
                        target_iso: str, batch_size: int = 8) -> "list[str]":
        """批量翻译多句，返回译文列表。"""
        from .languages import nllb_code
        src, tgt = nllb_code(source_iso), nllb_code(target_iso)
        self._load()

        # 过滤空句
        valid_idx = [i for i, t in enumerate(texts) if t and t.strip()]
        if not valid_idx:
            return [""] * len(texts)

        results = [""] * len(texts)
        tok = self._tok
        # NLLB 使用 src_lang / tgt_lang 控制特殊符号
        import torch
        for start in range(0, len(valid_idx), batch_size):
            chunk_idx = valid_idx[start:start + batch_size]
            chunk = [texts[i].strip() for i in chunk_idx]
            enc = tok(
                chunk,
                padding=True,
                truncation=True,
                max_length=1024,
                return_tensors="pt",
                src_lang=src,
            ).to(self.device)
            with torch.no_grad():
                gen = self._model.generate(
                    **enc,
                    forced_bos_token_id=tok.convert_tokens_to_ids(tgt),
                    max_new_tokens=self.max_new_tokens,
                    max_length=None,
                    num_beams=self.beam_size,
                )
            outs = tok.batch_decode(gen, skip_special_tokens=True)
            for local_i, global_i in enumerate(chunk_idx):
                results[global_i] = (outs[local_i] or "").strip()
        return results
