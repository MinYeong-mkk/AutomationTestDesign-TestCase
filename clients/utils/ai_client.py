import json
import os
from typing import Any

from anthropic import Anthropic
from openai import OpenAI


_clients = {}
_provider = os.getenv("AI_PROVIDER", "openai").lower()
_model = os.getenv("OPENAI_MODEL", "gpt-4o")
_usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

MODEL_PRICING_USD_PER_MILLION = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
}


def configure(provider: str, model: str = None) -> None:
    """이번 실행에서 사용할 AI provider/model을 지정한다."""
    global _provider, _model
    provider = provider.strip().lower()
    if provider not in {"openai", "anthropic"}:
        raise ValueError(f"지원하지 않는 AI provider입니다: {provider}")
    required_key = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    if not os.getenv(required_key):
        raise RuntimeError(f"{provider} 사용을 위해 .env에 {required_key}를 설정해주세요.")
    _provider = provider
    _model = model or (
        os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        if provider == "anthropic"
        else os.getenv("OPENAI_MODEL", "gpt-4o")
    )
    reset_usage()


def current_config() -> tuple[str, str]:
    return _provider, _model


def reset_usage() -> None:
    _usage.update({"input_tokens": 0, "output_tokens": 0, "calls": 0})


def usage_summary() -> dict:
    input_price, output_price = MODEL_PRICING_USD_PER_MILLION.get(_model, (0, 0))
    estimated_cost = (
        _usage["input_tokens"] * input_price
        + _usage["output_tokens"] * output_price
    ) / 1_000_000
    return {
        "provider": _provider,
        "model": _model,
        **_usage,
        "estimated_cost_usd": round(estimated_cost, 4),
        "pricing_known": bool(input_price or output_price),
    }


def _client(provider: str):
    if provider not in _clients:
        if provider == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError("Claude 사용을 위해 .env에 ANTHROPIC_API_KEY를 설정해주세요.")
            _clients[provider] = Anthropic(api_key=key)
        else:
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OpenAI 사용을 위해 .env에 OPENAI_API_KEY를 설정해주세요.")
            _clients[provider] = OpenAI(api_key=key)
    return _clients[provider]


def _record_usage(input_tokens: int, output_tokens: int) -> None:
    _usage["input_tokens"] += input_tokens or 0
    _usage["output_tokens"] += output_tokens or 0
    _usage["calls"] += 1


def chat(
    prompt: str,
    system: str = None,
    max_tokens: int = 4000,
    images: list = None,
    model: str = None,
) -> str:
    """선택된 OpenAI/Anthropic 모델을 호출하고 JSON 문자열을 반환한다."""
    selected_model = model or _model
    system_text = "You must respond with valid JSON only. Do not include markdown or explanations."
    if system:
        system_text += f"\n{system}"

    if _provider == "anthropic":
        content = [{"type": "text", "text": prompt}]
        for img in images or []:
            content.append({"type": "text", "text": f"[화면: {img['description']}]"})
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("media_type", "image/png"),
                    "data": img["image"],
                },
            })
        # 한국어 상세 JSON은 동일 글자 수 대비 토큰이 커서 12k에서 자주 잘린다.
        effective_max_tokens = max(max_tokens, 32000) if max_tokens >= 8000 else max_tokens
        with _client("anthropic").messages.stream(
            model=selected_model,
            max_tokens=effective_max_tokens,
            system=system_text,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            response = stream.get_final_message()
        _record_usage(response.usage.input_tokens, response.usage.output_tokens)
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                f"Claude 응답이 {effective_max_tokens:,} output tokens에서 잘렸습니다. "
                "입력 범위를 줄이거나 산출물을 분할해주세요."
            )
        return text

    content = [{"type": "text", "text": prompt}]
    for img in images or []:
        content.append({"type": "text", "text": f"[화면: {img['description']}]"})
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img.get('media_type', 'image/png')};base64,{img['image']}",
                "detail": "high",
            },
        })
    response = _client("openai").chat.completions.create(
        model=selected_model,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": content},
        ],
    )
    _record_usage(response.usage.prompt_tokens, response.usage.completion_tokens)
    return response.choices[0].message.content.strip()


def chat_json(
    prompt: str,
    system: str = None,
    max_tokens: int = 4000,
    images: list = None,
    model: str = None,
) -> Any:
    text = chat(prompt, system=system, max_tokens=max_tokens, images=images, model=model)
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("\n=== JSON 파싱 실패 ===")
        print(text[:2000])
        print("=====================\n")
        raise
