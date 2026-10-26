"""The vision judge run through OpenRouter, so any vision model can be compared.

Same rubric, images and parsing as VisionJudge (Gemini direct); only the API
call differs. Used by scripts/judge_compare.py on the company OpenRouter key.
"""

import io
import threading
import time
from pathlib import Path

import httpx
from PIL import Image

from backend.qa.corpus import Candidate
from backend.qa.judge import JudgeResult, VisionJudge, judge_images, rubric_prompt
from backend.qa.thumbs import jpeg_data_url, thumbnail_jpeg

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Claude downsizes anything larger anyway; sending less keeps uploads quick.
_MAX_EDGE = 1568


CORNER_NOTE = """
CLOSE-UPS: after this text come two more images: a close-up of the TOP-LEFT CORNER of the
SAMPLE door, then the same corner of the GENERATED door. Base profile_character_match on
them: compare the inside edge where frame meets panel (square, beveled, ogee, bead), any
applied molding, the panel's raise or recess, and how stiles and rails join.
"""


def _image_part(jpeg: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": jpeg_data_url(jpeg)}}


class OpenRouterJudge(VisionJudge):
    def __init__(
        self,
        api_key: str,
        model: str,
        cache_dir: Path = Path("output/.qa/verdicts"),
        http: httpx.Client | None = None,
        ignore_shape: bool = False,
        corners: bool = False,
    ) -> None:
        # No Gemini client: every call goes through _judge_once below.
        super().__init__(api_key="", model=model, cache_dir=cache_dir, client=object())
        self._api_key = api_key
        self.ignore_shape = ignore_shape
        self.corners = corners
        self.prompt_variant = "+".join(
            name for name, on in (("ignore_shape", ignore_shape), ("corners", corners)) if on
        )
        self._http = http or httpx.Client(timeout=180)
        self._cost_lock = threading.Lock()
        self.cost_usd = 0.0  # spend on uncached calls this session (OpenRouter-reported)

    def _judge_once(self, candidate: Candidate) -> JudgeResult:
        try:
            content: list[dict] = [
                _image_part(thumbnail_jpeg(path, _MAX_EDGE, quality=92))
                for path in judge_images(candidate)
            ]
            corners = []
            if self.corners and candidate.sample_path is not None:
                corners = [
                    _image_part(door_corner(candidate.sample_path)),
                    _image_part(door_corner(candidate.image_path)),
                ]
        except OSError as exc:
            return JudgeResult(
                key=candidate.key, verdict="error", reason=f"unreadable image: {exc}"
            )
        prompt = rubric_prompt(candidate, self.ignore_shape)
        content.append({"type": "text", "text": prompt + (CORNER_NOTE if corners else "")})
        content.extend(corners)
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 1500,
            "usage": {"include": True},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        last_error = ""
        bad_outputs = 0
        for attempt in range(4):
            if attempt:
                time.sleep(2 ** (attempt - 1))
            try:
                resp = self._http.post(OPENROUTER_URL, json=body, headers=headers)
            except httpx.HTTPError as exc:  # network: transient
                last_error = f"api error: {exc}"
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"api error: HTTP {resp.status_code}"
                continue
            if resp.status_code >= 400:  # bad key, no credit, bad request: retrying won't help
                return JudgeResult(
                    key=candidate.key,
                    verdict="error",
                    reason=f"api error: HTTP {resp.status_code} {resp.text[:200]}",
                )
            try:
                data = resp.json()
                with self._cost_lock:
                    self.cost_usd += float((data.get("usage") or {}).get("cost") or 0)
                text = data["choices"][0]["message"]["content"] or ""
                return self._parse(candidate.key, text)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                # Each retry is billed: one more try, then give up.
                last_error = f"unparseable response: {exc}"
                bad_outputs += 1
                if bad_outputs >= 2:
                    break
        return JudgeResult(key=candidate.key, verdict="error", reason=last_error)


def door_corner(path: Path, size: int = 768) -> bytes:
    """Close-up of the door's top-left corner (frame joint, edge profile, panel edge).

    The door is found as the non-white area of the photo; the crop is a square
    45% of the door's width, so it shows the same detail at any image size.
    """
    with Image.open(path) as img:
        rgb = img.convert("RGB")
    mask = rgb.convert("L").point(lambda v: 255 if v < 235 else 0)
    left, top, right, _ = mask.getbbox() or (0, 0, *rgb.size)
    side = max(16, int((right - left) * 0.45))
    crop = rgb.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=92)
    return out.getvalue()
