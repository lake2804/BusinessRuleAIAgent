"""LLM Factory."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class LLMResponse:
    content: str
    model: str


class LLMProvider(ABC):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @abstractmethod
    async def complete(self, messages: List[Dict], **kwargs) -> LLMResponse:
        pass
    
    def format_messages(self, system: Optional[str], user: str) -> List[Dict]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return messages


class GroqProvider(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        try:
            import groq
            if not self._client:
                self._client = groq.Groq(api_key=self.api_key)
            
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', 0.1),
                max_tokens=kwargs.get('max_tokens', 4000)
            )
            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model
            )
        except Exception as e:
            return LLMResponse(content=f"Error: {str(e)}", model="error")


class OpenAIProvider(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        try:
            import openai
            if not self._client:
                self._client = openai.AsyncOpenAI(api_key=self.api_key)
            
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', 0.1)
            )
            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model
            )
        except Exception as e:
            return LLMResponse(content=f"Error: {str(e)}", model="error")


class LLMFactory:
    _providers = {"groq": GroqProvider, "openai": OpenAIProvider}
    
    @classmethod
    def create(cls, provider_name: str, api_key: str, model: str) -> LLMProvider:
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")
        return provider_class(api_key, model)
