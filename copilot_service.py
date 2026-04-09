"""GitHub Copilot SDK integration for Reader3 summaries."""

from __future__ import annotations

import base64
import os
from typing import Any

try:
    from copilot import CopilotClient
    from copilot.session import PermissionHandler
except ImportError:  # pragma: no cover - exercised through runtime status checks
    CopilotClient = None
    PermissionHandler = None


DEFAULT_COPILOT_MODEL = os.environ.get("READER3_COPILOT_MODEL", "claude-sonnet-4")
DEFAULT_TIMEOUT_SECONDS = float(
    os.environ.get("READER3_COPILOT_TIMEOUT_SECONDS", "90")
)

COPILOT_SUMMARY_SYSTEM_MESSAGE = (
    "You are Reader3, a careful reading assistant. "
    "Summarize only the text or image content supplied in the current request. "
    "Do not invent details that are not supported by the supplied material. "
    "If the source is unclear, incomplete, or ambiguous, say so plainly."
)


class CopilotSummaryError(RuntimeError):
    """Raised when Reader3 cannot complete a Copilot summary request."""


class CopilotSummaryService:
    """Thin wrapper around the Python Copilot SDK for one-shot summaries."""

    def __init__(
        self,
        *,
        model: str | None = None,
        client: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.model = model or DEFAULT_COPILOT_MODEL
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._runtime_started = False
        self._startup_error: str | None = None

    async def start(self) -> str | None:
        """Prepare the SDK client without forcing a runtime connection."""
        if self._client is not None:
            self._startup_error = None
            return None

        if CopilotClient is None:
            self._startup_error = (
                "github-copilot-sdk is not installed. "
                "Run `uv sync` to enable Reader3 summaries."
            )
            return self._startup_error

        try:
            self._client = CopilotClient()
            self._startup_error = None
            return None
        except Exception as exc:  # pragma: no cover - depends on SDK runtime
            self._startup_error = str(exc)
            self._client = None
            return self._startup_error

    async def stop(self) -> None:
        """Stop the SDK runtime when Reader3 shuts down."""
        if not self._owns_client or self._client is None or not self._runtime_started:
            return

        try:
            await self._client.stop()
        finally:
            self._runtime_started = False

    async def get_status(self) -> dict[str, Any]:
        """Return a lightweight SDK status snapshot for the UI."""
        status = {
            "available": False,
            "authenticated": False,
            "model": self.model,
            "supports_vision": None,
            "error": self._startup_error,
        }

        try:
            client = await self._ensure_runtime_started()
        except CopilotSummaryError as exc:
            status["error"] = str(exc)
            return status

        try:
            models = await client.list_models()
        except Exception as exc:  # pragma: no cover - network/auth dependent
            status["error"] = str(exc)
            return status

        status["authenticated"] = True
        model_info = self._find_model_info(models, self.model)
        if model_info is None:
            status["error"] = (
                f"Configured Copilot model '{self.model}' is not available."
            )
            return status

        status["available"] = True
        status["supports_vision"] = self._extract_vision_support(model_info)
        return status

    async def summarize_text(
        self,
        text: str,
        *,
        scope: str,
        book_title: str | None = None,
        chapter_title: str | None = None,
    ) -> str:
        """Summarize chapter text or a selected passage."""
        prompt = self._build_text_prompt(
            text,
            scope=scope,
            book_title=book_title,
            chapter_title=chapter_title,
        )
        return await self._send_prompt(prompt)

    async def summarize_image_file(
        self,
        image_path: str,
        *,
        book_title: str | None = None,
        chapter_title: str | None = None,
    ) -> str:
        """Summarize an on-disk image using a file attachment."""
        prompt = self._build_image_prompt(
            book_title=book_title,
            chapter_title=chapter_title,
        )
        attachments = [
            {
                "type": "file",
                "path": os.path.abspath(image_path),
                "displayName": os.path.basename(image_path),
            }
        ]
        return await self._send_prompt(prompt, attachments=attachments)

    async def summarize_image_blob(
        self,
        image_bytes: bytes,
        *,
        mime_type: str,
        display_name: str,
        book_title: str | None = None,
        chapter_title: str | None = None,
    ) -> str:
        """Summarize in-memory image bytes using a blob attachment."""
        prompt = self._build_image_prompt(
            book_title=book_title,
            chapter_title=chapter_title,
        )
        attachments = [
            {
                "type": "blob",
                "data": base64.b64encode(image_bytes).decode("ascii"),
                "mimeType": mime_type,
                "displayName": display_name,
            }
        ]
        return await self._send_prompt(prompt, attachments=attachments)

    async def _send_prompt(
        self,
        prompt: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str:
        """Send a single summary request through a short-lived Copilot session."""
        client = await self._ensure_runtime_started()
        session = await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=self.model,
            client_name="Reader3",
            available_tools=[],
            system_message={
                "mode": "replace",
                "content": COPILOT_SUMMARY_SYSTEM_MESSAGE,
            },
        )

        try:
            response = await session.send_and_wait(
                prompt,
                attachments=attachments,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            raise CopilotSummaryError(str(exc)) from exc
        finally:
            try:
                await session.disconnect()
            except Exception:
                pass

        content = self._extract_response_content(response)
        if not content:
            raise CopilotSummaryError("Copilot returned an empty response.")
        return content.strip()

    async def _ensure_runtime_started(self):
        """Create and start the underlying SDK runtime on first use."""
        if self._client is None:
            await self.start()

        if self._client is None:
            raise CopilotSummaryError(
                self._startup_error or "Copilot SDK client is unavailable."
            )

        if self._runtime_started:
            return self._client

        try:
            await self._client.start()
        except Exception as exc:
            self._startup_error = str(exc)
            raise CopilotSummaryError(str(exc)) from exc

        self._runtime_started = True
        self._startup_error = None
        return self._client

    def _build_text_prompt(
        self,
        text: str,
        *,
        scope: str,
        book_title: str | None,
        chapter_title: str | None,
    ) -> str:
        scope_label = "selected passage" if scope == "selection" else "chapter"
        context_lines = []
        if book_title:
            context_lines.append(f"Book: {book_title}")
        if chapter_title:
            context_lines.append(f"Section: {chapter_title}")

        context_prefix = "\n".join(context_lines)
        if context_prefix:
            context_prefix += "\n\n"

        return (
            f"Summarize this {scope_label} for a reader. "
            "Keep the answer concise but useful, and call out the central idea, "
            "important details, and any uncertainty.\n\n"
            f"{context_prefix}"
            f"Text to summarize:\n\"\"\"{text}\"\"\""
        )

    def _build_image_prompt(
        self,
        *,
        book_title: str | None,
        chapter_title: str | None,
    ) -> str:
        context_lines = []
        if book_title:
            context_lines.append(f"Book: {book_title}")
        if chapter_title:
            context_lines.append(f"Section: {chapter_title}")

        context_prefix = "\n".join(context_lines)
        if context_prefix:
            context_prefix += "\n\n"

        return (
            "Describe and summarize the attached image for a reader. "
            "Focus on what is visibly present, why it seems relevant, and any "
            "text or labels that can be read. If the image is unclear, say so.\n\n"
            f"{context_prefix}"
            "Return plain text only."
        )

    def _find_model_info(self, models: list[Any], model_name: str) -> Any | None:
        for model in models:
            if self._read_value(model, "id", "name", "model") == model_name:
                return model
        return None

    def _extract_vision_support(self, model_info: Any) -> bool | None:
        direct = self._read_value(model_info, "supports_vision")
        if isinstance(direct, bool):
            return direct

        capabilities = self._read_value(model_info, "capabilities")
        supports = self._read_value(capabilities, "supports")
        vision = self._read_value(supports, "vision")
        if isinstance(vision, bool):
            return vision
        return None

    def _extract_response_content(self, response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response

        data = getattr(response, "data", None)
        if data is not None:
            content = getattr(data, "content", None)
            if isinstance(content, str):
                return content

        if isinstance(response, dict):
            payload = response.get("data", response)
            if isinstance(payload, dict):
                content = payload.get("content")
                if isinstance(content, str):
                    return content
        return ""

    def _read_value(self, obj: Any, *keys: str) -> Any:
        if obj is None:
            return None

        for key in keys:
            if isinstance(obj, dict) and key in obj:
                return obj[key]
            if hasattr(obj, key):
                return getattr(obj, key)
        return None