import logging

import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "mistral-nemo:12b"
SYSTEM_PROMPT = (
    "Eres el asistente virtual de Huellitas, una plataforma colombiana de adopción de mascotas. "
    "Ayudas a las personas con preguntas sobre adopciones, fundaciones, mascotas disponibles "
    "y el proceso de adopción. Responde siempre en español, de forma amable y concisa. "
    "Si no sabes algo, dilo con honestidad en lugar de inventar información."
)


def chat(messages: list[dict]) -> str:
    ollama_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in messages
    ]
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": ollama_messages, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]
