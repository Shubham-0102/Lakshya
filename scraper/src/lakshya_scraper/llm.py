"""The one place that calls an AI model, so changing provider touches only this file.

Llm.structured() asks for JSON matching a Pydantic model and returns that model, trying the
next model when one is busy. The Gemini call itself sits behind `Send`, so tests use a fake
and need no network or API key.

Only public job text may go through here while we're on a free tier: Google may use free-tier
content to improve its products, and people may read it. CVs never go through a free tier.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import types

# The SDK has no public name for the errors its interactions API raises. uv.lock pins the
# version, and if an upgrade moves them this import fails loudly at startup.
from google.genai._gaos.lib.compat_errors import APIConnectionError, APIStatusError
from pydantic import BaseModel, ValidationError

from lakshya_backend.config import get_settings

logger = logging.getLogger(__name__)

Output = TypeVar("Output", bound=BaseModel)
_NOT_FOUND = 404
_TOO_MANY_REQUESTS = 429
_SERVER_ERRORS = 500
_NEVER_SENT = 599


@dataclass(frozen=True)
class Reply:
    text: str
    input_tokens: int
    output_tokens: int  # includes the tokens the model spent thinking


class LlmError(Exception):
    """No answer: every model failed, or the request itself was refused (e.g. a bad key)."""


class ModelBusy(Exception):
    """Overloaded for now: worth waiting and trying this model again."""


class SkipModel(Exception):
    """This model can't answer today (quota used, or retired): go to the next one."""


Send = Callable[[str, str, dict], Reply]  # (model, prompt, JSON schema) -> reply


class Llm:
    def __init__(
        self,
        send: Send,
        models: list[str],
        attempts: int = 2,
        wait_seconds: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._send = send
        self._models = models
        self._attempts = attempts
        self._wait_seconds = wait_seconds
        self._sleep = sleep

    def structured(self, prompt: str, schema: type[Output], purpose: str) -> Output:
        """Ask for a `schema` object. `purpose` labels the call in the logs, for measuring cost."""
        for model in self._models:
            try:
                if (result := self._ask_model(model, prompt, schema, purpose)) is not None:
                    return result
            except SkipModel as skip:
                logger.warning("llm %s: skipping %s: %s", purpose, model, skip)
        raise LlmError(f"no model gave a usable answer for {purpose}: {self._models}")

    def _ask_model(
        self, model: str, prompt: str, schema: type[Output], purpose: str
    ) -> Output | None:
        for attempt in range(self._attempts):
            if attempt:
                self._sleep(self._wait_seconds)
            started = time.monotonic()
            try:
                reply = self._send(model, prompt, schema.model_json_schema())
            except ModelBusy as busy:
                logger.warning("llm %s: %s is busy: %s", purpose, model, busy)
                continue
            # Never log the prompt or the reply: the tokens are all we need for the cost metric
            logger.info(
                "llm %s: model=%s input_tokens=%d output_tokens=%d seconds=%.1f",
                purpose,
                model,
                reply.input_tokens,
                reply.output_tokens,
                time.monotonic() - started,
            )
            try:
                return schema.model_validate_json(reply.text)
            except ValidationError as error:
                logger.warning(
                    "llm %s: %s broke the format: %d errors", purpose, model, error.error_count()
                )
        return None


def _within[Result](seconds: float, call: Callable[[], Result]) -> Result:
    """Give up on `call` after `seconds`, however it's getting on. The SDK's own timeout isn't
    a deadline: it restarts when any bytes arrive, and a real call ran for over 5 minutes on a
    90 second timeout. The thread is a daemon, so one that never returns can't stop us exiting."""
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["value"] = call()
        except Exception as error:
            outcome["error"] = error

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise ModelBusy(f"no answer within {seconds:.0f} s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def gemini_client(api_key: str | None) -> genai.Client:
    """No retries in the SDK. It obeys the server's Retry-After, so a used-up daily quota (20
    requests per model on the free tier) could hold a call for hours instead of telling us to
    try the next model. `attempts` can't turn this off: it means retries, and 0 becomes 1. So
    retries are limited to a status code no server sends."""
    retries = types.HttpRetryOptions(http_status_codes=[_NEVER_SENT])
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(retry_options=retries))


def gemini_sender(client: genai.Client, timeout_seconds: float = 120.0) -> Send:
    def ask(model: str, prompt: str, schema: dict):
        return client.interactions.create(
            model=model,
            input=prompt,
            store=False,  # no copy of the conversation is kept on Google's side
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
            timeout=timeout_seconds,
        )

    def send(model: str, prompt: str, schema: dict) -> Reply:
        try:
            response = _within(timeout_seconds, lambda: ask(model, prompt, schema))
        except APIConnectionError as error:  # includes timeouts
            raise ModelBusy(type(error).__name__) from error
        except APIStatusError as error:
            raise _meaning_of(error) from error

        usage = response.usage
        return Reply(
            text=response.output_text or "",
            input_tokens=usage.total_input_tokens or 0,
            output_tokens=(usage.total_output_tokens or 0) + (usage.total_thought_tokens or 0),
        )

    return send


def _meaning_of(error: APIStatusError) -> Exception:
    status = error.status_code
    if status >= _SERVER_ERRORS:
        return ModelBusy(f"HTTP {status}")
    if status in (_NOT_FOUND, _TOO_MANY_REQUESTS):
        return SkipModel(f"HTTP {status}")
    # Retrying can't fix a bad key or a bad request, so stop here
    return LlmError(f"the request was refused: HTTP {status}")


@lru_cache
def get_llm() -> Llm:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LlmError("GEMINI_API_KEY is not set. Add it to .env (see .env.example).")
    client = gemini_client(settings.gemini_api_key)
    return Llm(gemini_sender(client), settings.gemini_models.split(","))
