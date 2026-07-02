"""LLM vision judge: compare a generated image against its sample photo and swatch."""

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from google import genai
from google.genai import types

from backend.qa.corpus import Candidate

DEFAULT_MODEL = "gemini-3-pro-preview"

RUBRIC_PROMPT = """You are a strict quality inspector for AI-generated cabinet door product images.
The first image is the customer's SAMPLE photo of the real door.{swatch_line}
The LAST image is the AI-GENERATED {kind} being judged.

Decide whether the generated image is usable as a product photo of the SAME door design
{material_line}. Be strict: subtle geometry or profile changes make an image unusable.

Score each criterion 1-5 (5 = indistinguishable from the sample, 1 = clearly wrong):
- panel_layout_match: same count and arrangement of panels, stiles, rails
- proportions_match: stile/rail widths and panel proportions match the sample
- profile_character_match: edge profile, bevels, routing detail read as the same product
- material_realism: wood grain and finish look photographically real, plausible grain direction
- swatch_fidelity: color and species match the swatch image (score 5 if no swatch was provided)

Also list artifacts you see: warping, added or removed hardware, changed corners, blur,
text or watermark remnants, inconsistent lighting or shadows.

Reply with ONLY a JSON object, no markdown fences:
{{"panel_layout_match": n, "proportions_match": n, "profile_character_match": n,
"material_realism": n, "swatch_fidelity": n, "artifacts": ["..."],
"verdict": "pass" or "fail", "confidence": "high" or "low", "reason": "one sentence"}}"""


@dataclass
class JudgeResult:
    key: str
    panel_layout_match: int = 0
    proportions_match: int = 0
    profile_character_match: int = 0
    material_realism: int = 0
    swatch_fidelity: int = 0
    artifacts: list[str] = field(default_factory=list)
    verdict: str = "error"  # "pass" | "fail" | "error"
    confidence: str = "low"  # "high" | "low"
    reason: str = ""
    votes: int = 1


def _mime(data: bytes) -> str:
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def _image_part(path: Path) -> types.Part:
    data = path.read_bytes()
    return types.Part.from_bytes(data=data, mime_type=_mime(data))


class VisionJudge:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        cache_dir: Path = Path("output/.qa/verdicts"),
        client: object | None = None,
    ) -> None:
        self.client = client or genai.Client(api_key=api_key)
        self.model = model
        self.cache_dir = cache_dir

    def config_hash(self) -> str:
        return hashlib.sha256(f"{self.model}|{RUBRIC_PROMPT}".encode()).hexdigest()[:12]

    def _cache_path(self, key: str) -> Path:
        safe = key.replace(":", "_")
        return self.cache_dir / self.config_hash() / f"{safe}.json"

    def judge(self, candidate: Candidate) -> JudgeResult:
        cache = self._cache_path(candidate.key)
        if cache.exists():
            return JudgeResult(**json.loads(cache.read_text()))

        result = self._judge_once(candidate)
        if result.verdict != "error" and result.confidence == "low":
            votes = [result, self._judge_once(candidate), self._judge_once(candidate)]
            fails = sum(1 for v in votes if v.verdict in ("fail", "error"))
            result.verdict = "fail" if fails >= 2 else "pass"
            result.confidence = "high" if fails in (0, 3) else "low"
            result.votes = 3

        if result.verdict != "error":
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(asdict(result)))
        return result

    def _judge_once(self, candidate: Candidate) -> JudgeResult:
        prompt = RUBRIC_PROMPT.format(
            swatch_line=(
                "\nThe middle image is the target WOOD SWATCH for this variant."
                if candidate.swatch_path
                else ""
            ),
            kind=candidate.kind,
            material_line=(
                f" rendered in {candidate.wood_name}" if candidate.wood_name else ""
            ),
        )
        try:
            parts: list[types.Part] = []
            if candidate.sample_path is not None:
                parts.append(_image_part(candidate.sample_path))
            if candidate.swatch_path is not None:
                parts.append(_image_part(candidate.swatch_path))
            parts.append(_image_part(candidate.image_path))
            parts.append(types.Part.from_text(text=prompt))
        except OSError as exc:
            reason = f"unreadable image: {exc}"
            return JudgeResult(key=candidate.key, verdict="error", reason=reason)
        contents = [types.Content(role="user", parts=parts)]

        last_error = ""
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=contents
                )
            except Exception as exc:  # network/API errors -> retry with backoff then error verdict
                last_error = f"api error: {exc}"
                time.sleep(2**attempt)
                continue
            try:
                return self._parse(candidate.key, response.text or "")
            except (json.JSONDecodeError, KeyError, ValueError, AttributeError, TypeError) as exc:
                last_error = f"unparseable response: {exc}"
        return JudgeResult(key=candidate.key, verdict="error", reason=last_error)

    def _parse(self, key: str, text: str) -> JudgeResult:
        cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        if data.get("verdict") not in ("pass", "fail"):
            raise ValueError(f"bad verdict: {data.get('verdict')!r}")
        return JudgeResult(
            key=key,
            panel_layout_match=int(data["panel_layout_match"]),
            proportions_match=int(data["proportions_match"]),
            profile_character_match=int(data["profile_character_match"]),
            material_realism=int(data["material_realism"]),
            swatch_fidelity=int(data["swatch_fidelity"]),
            artifacts=[str(a) for a in data.get("artifacts", [])],
            verdict=data["verdict"],
            confidence=data.get("confidence", "low"),
            reason=str(data.get("reason", "")),
        )
