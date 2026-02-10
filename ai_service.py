"""
AI Service for Reader3.
Provides LLM-powered features using free providers:
- Ollama (local, completely free)
- Google Gemini (cloud, free tier)
"""

import json
import os
from typing import Optional, Literal
from dataclasses import dataclass
import httpx


@dataclass
class AIConfig:
    """Configuration for AI service."""
    provider: Literal["ollama", "gemini"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gpt-oss:120b-cloud"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"


class AIService:
    """
    AI Service that supports multiple LLM providers.
    Reuses a persistent httpx.AsyncClient for connection pooling.
    
    Usage:
        ai = AIService()
        response = await ai.ask("What does this mean?", "Some text context...")
        summary = await ai.summarize("Long chapter text...")
    """
    
    def __init__(self, config: Optional[AIConfig] = None):
        self.config = config or self._load_config()
        self._client: Optional[httpx.AsyncClient] = None
    
    def _load_config(self) -> AIConfig:
        """Load config from file or environment."""
        config_path = os.path.join(os.path.dirname(__file__), "ai_config.json")
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
                return AIConfig(
                    provider=data.get("provider", "ollama"),
                    ollama_base_url=data.get("ollama", {}).get("base_url", "http://localhost:11434"),
                    ollama_model=data.get("ollama", {}).get("model", "llama3.2"),
                    gemini_api_key=data.get("gemini", {}).get("api_key", "") or os.environ.get("GEMINI_API_KEY", ""),
                    gemini_model=data.get("gemini", {}).get("model", "gemini-1.5-flash"),
                )
            except Exception:
                pass
        
        # Default config with environment variable fallback
        return AIConfig(
            gemini_api_key=os.environ.get("GEMINI_API_KEY", "")
        )
    
    def save_config(self) -> None:
        """Save current config to file."""
        config_path = os.path.join(os.path.dirname(__file__), "ai_config.json")
        data = {
            "provider": self.config.provider,
            "ollama": {
                "base_url": self.config.ollama_base_url,
                "model": self.config.ollama_model,
            },
            "gemini": {
                "api_key": self.config.gemini_api_key,
                "model": self.config.gemini_model,
            }
        }
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Return a persistent httpx client (connection pooling)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def close(self):
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_availability(self) -> dict:
        """Check if the AI service is available."""
        result = {"available": False, "provider": self.config.provider, "model": "", "error": None}
        
        try:
            if self.config.provider == "ollama":
                client = await self._get_client()
                response = await client.get(
                    f"{self.config.ollama_base_url}/api/tags",
                    timeout=5.0,
                )
                if response.status_code == 200:
                    result["available"] = True
                    result["model"] = self.config.ollama_model
                    # Check if the configured model is available
                    models = response.json().get("models", [])
                    model_names = [m.get("name", "").split(":")[0] for m in models]
                    if self.config.ollama_model.split(":")[0] not in model_names:
                        result["error"] = f"Model '{self.config.ollama_model}' not found. Available: {', '.join(model_names[:5])}"
            
            elif self.config.provider == "gemini":
                if not self.config.gemini_api_key:
                    result["error"] = "Gemini API key not configured"
                else:
                    # Quick validation by listing models
                    client = await self._get_client()
                    response = await client.get(
                        f"https://generativelanguage.googleapis.com/v1beta/models?key={self.config.gemini_api_key}",
                        timeout=5.0,
                    )
                    if response.status_code == 200:
                        result["available"] = True
                        result["model"] = self.config.gemini_model
                    else:
                        result["error"] = "Invalid API key"
        
        except httpx.ConnectError:
            result["error"] = "Cannot connect to Ollama. Is it running?" if self.config.provider == "ollama" else "Network error"
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    async def ask(self, question: str, context: str, book_title: str = "") -> str:
        """
        Answer a question about the given text context.
        
        Args:
            question: The user's question
            context: The selected text to ask about
            book_title: Optional book title for context
        
        Returns:
            The AI's response
        """
        prompt = self._build_ask_prompt(question, context, book_title)
        return await self._generate(prompt)
    
    async def summarize(self, text: str, style: Literal["concise", "detailed", "bullets"] = "concise") -> str:
        """
        Summarize the given text.
        
        Args:
            text: The text to summarize
            style: Summary style - concise, detailed, or bullets
        
        Returns:
            The summary
        """
        prompt = self._build_summarize_prompt(text, style)
        return await self._generate(prompt)
    
    async def explain(self, text: str) -> str:
        """Explain the given text in simpler terms."""
        prompt = f"""Explain the following text in simple, easy-to-understand terms. 
Break down any complex concepts and use everyday language.

Text to explain:
\"\"\"{text}\"\"\"

Explanation:"""
        return await self._generate(prompt)
    
    async def define(self, word: str, context: str = "") -> str:
        """Get a definition for a word, optionally with context."""
        if context:
            prompt = f"""Define the word "{word}" as it is used in this context:
\"\"\"{context}\"\"\"

Provide:
1. The definition in this context
2. Part of speech
3. A simple example sentence"""
        else:
            prompt = f"""Define the word "{word}".

Provide:
1. Definition
2. Part of speech  
3. A simple example sentence"""
        
        return await self._generate(prompt)
    
    def _build_ask_prompt(self, question: str, context: str, book_title: str) -> str:
        """Build the prompt for asking questions."""
        book_context = f" from the book '{book_title}'" if book_title else ""
        
        return f"""You are a helpful reading assistant. Answer the user's question about the following text passage{book_context}.

Be concise but thorough. If the question cannot be answered from the given context, say so.

Text passage:
\"\"\"{context}\"\"\"

Question: {question}

Answer:"""
    
    def _build_summarize_prompt(self, text: str, style: str) -> str:
        """Build the prompt for summarization."""
        style_instructions = {
            "concise": "Provide a concise summary in 2-3 sentences capturing the main points.",
            "detailed": "Provide a detailed summary covering all key points, themes, and important details. Use multiple paragraphs if needed.",
            "bullets": "Summarize the key points as a bulleted list. Include 5-10 bullet points covering the main ideas.",
        }
        
        instruction = style_instructions.get(style, style_instructions["concise"])
        
        return f"""Summarize the following text.

{instruction}

Text to summarize:
\"\"\"{text}\"\"\"

Summary:"""
    
    async def _generate(self, prompt: str) -> str:
        """Generate a response using the configured provider."""
        if self.config.provider == "ollama":
            return await self._ollama_generate(prompt)
        elif self.config.provider == "gemini":
            return await self._gemini_generate(prompt)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")
    
    async def _ollama_generate(self, prompt: str) -> str:
        """Generate using Ollama's local API."""
        client = await self._get_client()
        response = await client.post(
            f"{self.config.ollama_base_url}/api/generate",
            json={
                "model": self.config.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 1024,
                }
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama error: {response.text}")
        
        return response.json().get("response", "").strip()
    
    async def _gemini_generate(self, prompt: str) -> str:
        """Generate using Google Gemini's API."""
        if not self.config.gemini_api_key:
            raise Exception("Gemini API key not configured. Set GEMINI_API_KEY or configure in settings.")
        
        client = await self._get_client()
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.gemini_model}:generateContent",
            params={"key": self.config.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1024,
                }
            },
            timeout=60.0,
        )
            
            if response.status_code != 200:
                error_msg = response.json().get("error", {}).get("message", response.text)
                raise Exception(f"Gemini error: {error_msg}")
            
            # Extract text from Gemini response
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            
            return ""


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get or create the AI service singleton."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


def reset_ai_service() -> None:
    """Reset the AI service (useful after config changes)."""
    global _ai_service
    _ai_service = None
