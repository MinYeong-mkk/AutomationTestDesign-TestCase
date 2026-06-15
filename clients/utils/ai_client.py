import os
import json
from openai import OpenAI

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def chat(prompt: str, system: str = None, max_tokens: int = 4000, images: list = None) -> str:
    """OpenAI chat 호출 공통 래퍼. JSON 응답 기대 시 그대로 반환."""
    messages_content = []

    if system:
        messages_content.append({"type": "text", "text": system})
    messages_content.append({"type": "text", "text": prompt})

    if images:
        for img in images:
            messages_content.append({"type": "text", "text": f"\n[화면: {img['description']} | URL: {img['url']}]"})
            messages_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img['image']}", "detail": "low"}
            })

    response = get_client().chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You must respond with valid JSON only. Do not include markdown, code fences, or explanations."
            },
            {
                "role": "user",
                "content": messages_content
            }
        ]
    )
    return response.choices[0].message.content.strip()


def chat_json(prompt: str, system: str = None, max_tokens: int = 4000, images: list = None) -> any:
    """JSON 응답을 파싱해서 반환"""
    text = chat(prompt, system=system, max_tokens=max_tokens, images=images)
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print("\n=== JSON 파싱 실패 ===")
        print(text[:2000])
        print("=====================\n")
        raise e
