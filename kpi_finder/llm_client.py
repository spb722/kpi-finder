import os

from openai import OpenAI
from pydantic import BaseModel


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )


def call_structured(model_cls: type[BaseModel], messages: list[dict]) -> BaseModel:
    """Call Groq with strict JSON Schema structured output and return a parsed Pydantic model."""
    client = _get_client()
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

    schema = model_cls.model_json_schema()
    # Groq strict structured output requires additionalProperties: false
    schema["additionalProperties"] = False

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": model_cls.__name__,
                "schema": schema,
                "strict": True,
            },
        },
    )

    return model_cls.model_validate_json(response.choices[0].message.content)
