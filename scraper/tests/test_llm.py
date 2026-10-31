"""The LLM wrapper with a fake model: no network and no API key needed."""

import logging

import httpx
import pytest
from google.genai._gaos.lib.compat_errors import (
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)
from pydantic import BaseModel

from lakshya_scraper import llm as llm_module
from lakshya_scraper.llm import Llm, LlmError, ModelBusy, Reply, SkipModel, gemini_sender, get_llm
from lakshya_scraper.recipes import Recipe

REQUEST = httpx.Request("POST", "https://generativelanguage.example.com")


class Answer(BaseModel):
    value: str


GOOD = Reply('{"value": "ok"}', input_tokens=120, output_tokens=8)


class FakeModels:
    """model -> what it does on each call, in order: a Reply to give or an exception to raise."""

    def __init__(self, **script):
        self.script = {model.replace("_", "-"): list(steps) for model, steps in script.items()}
        self.calls: list[str] = []
        self.schemas: list[dict] = []

    def __call__(self, model: str, prompt: str, schema: dict) -> Reply:
        self.calls.append(model)
        self.schemas.append(schema)
        step = self.script[model].pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def llm_with(models: FakeModels, sleeps: list | None = None) -> Llm:
    pause = sleeps.append if sleeps is not None else lambda seconds: None
    return Llm(models, list(models.script), attempts=2, wait_seconds=10, sleep=pause)


def test_returns_the_model_and_sends_its_schema():
    models = FakeModels(first=[GOOD])

    answer = llm_with(models).structured("prompt", Answer, "test")

    assert answer == Answer(value="ok")
    assert models.schemas == [Answer.model_json_schema()]


def test_busy_model_is_retried_after_a_wait():
    sleeps = []
    models = FakeModels(first=[ModelBusy("503"), GOOD])

    llm_with(models, sleeps).structured("prompt", Answer, "test")

    assert models.calls == ["first", "first"]
    assert sleeps == [10]


def test_model_that_stays_busy_falls_back_to_the_next():
    models = FakeModels(first=[ModelBusy("503"), ModelBusy("503")], second=[GOOD])

    llm_with(models).structured("prompt", Answer, "test")

    assert models.calls == ["first", "first", "second"]


def test_used_up_or_retired_model_is_skipped_without_retrying():
    sleeps = []
    models = FakeModels(first=[SkipModel("429")], second=[SkipModel("404")], third=[GOOD])

    llm_with(models, sleeps).structured("prompt", Answer, "test")

    assert models.calls == ["first", "second", "third"]
    assert sleeps == []


def test_a_reply_that_breaks_the_format_is_retried():
    bad = Reply('{"wrong": 1}', 10, 5)
    models = FakeModels(first=[bad, GOOD])

    assert llm_with(models).structured("prompt", Answer, "test").value == "ok"


def test_a_reply_that_is_not_json_is_retried():
    models = FakeModels(first=[Reply("Sure! Here it is:", 10, 5), GOOD])

    assert llm_with(models).structured("prompt", Answer, "test").value == "ok"


def test_every_model_failing_is_an_error_not_a_wrong_answer():
    models = FakeModels(first=[SkipModel("429")], second=[ModelBusy("503"), ModelBusy("503")])

    with pytest.raises(LlmError, match="no model gave a usable answer"):
        llm_with(models).structured("prompt", Answer, "test")


def test_a_refused_request_stops_at_once():
    models = FakeModels(first=[LlmError("bad key")], second=[GOOD])

    with pytest.raises(LlmError, match="bad key"):
        llm_with(models).structured("prompt", Answer, "test")

    assert models.calls == ["first"]


def test_tokens_are_logged_for_the_cost_metric(caplog):
    with caplog.at_level(logging.INFO, logger="lakshya_scraper.llm"):
        llm_with(FakeModels(first=[GOOD])).structured("prompt", Answer, "learn-recipe")

    assert "learn-recipe: model=first input_tokens=120 output_tokens=8" in caplog.text


def test_tokens_of_a_rejected_reply_are_still_counted(caplog):
    models = FakeModels(first=[Reply("nope", 50, 3), GOOD])

    with caplog.at_level(logging.INFO, logger="lakshya_scraper.llm"):
        llm_with(models).structured("prompt", Answer, "test")

    assert "input_tokens=50 output_tokens=3" in caplog.text


def test_prompts_and_replies_never_reach_the_logs(caplog):
    models = FakeModels(first=[Reply('{"value": "reply-text"}', 1, 1)])

    with caplog.at_level(logging.DEBUG, logger="lakshya_scraper.llm"):
        llm_with(models).structured("secret-prompt-text", Answer, "test")

    assert "secret-prompt-text" not in caplog.text
    assert "reply-text" not in caplog.text


def test_recipe_can_be_asked_for():
    schema = Recipe.model_json_schema()

    assert {"listing", "job"} <= set(schema["properties"])


# The real sender, with a stand-in for the SDK client


class Usage:
    total_input_tokens = 100
    total_output_tokens = 20
    total_thought_tokens = 30


class Response:
    output_text = '{"value": "ok"}'
    usage = Usage()


class FakeClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.interactions = self
        self.request: dict = {}

    def create(self, **request):
        self.request = request
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def status_error(error_class, status: int):
    return error_class("x", response=httpx.Response(status, request=REQUEST), body=None)


def test_sender_asks_for_json_and_counts_thinking_as_output():
    client = FakeClient(Response())

    reply = gemini_sender(client, timeout_seconds=30)("model-a", "prompt", {"type": "object"})

    assert reply == Reply('{"value": "ok"}', input_tokens=100, output_tokens=50)
    assert client.request["model"] == "model-a"
    assert client.request["store"] is False
    assert client.request["timeout"] == 30
    assert client.request["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": {"type": "object"},
    }


@pytest.mark.parametrize(
    ("outcome", "meaning"),
    [
        (status_error(InternalServerError, 503), ModelBusy),
        (status_error(InternalServerError, 500), ModelBusy),
        (APITimeoutError(request=REQUEST), ModelBusy),
        (status_error(RateLimitError, 429), SkipModel),
        (status_error(NotFoundError, 404), SkipModel),  # real: gemini-2.5-flash for new users
        (status_error(BadRequestError, 400), LlmError),  # real: an invalid API key
        (status_error(AuthenticationError, 401), LlmError),
    ],
)
def test_sender_turns_each_failure_into_what_it_means(outcome, meaning):
    with pytest.raises(meaning):
        gemini_sender(FakeClient(outcome))("model-a", "prompt", {})


def test_missing_api_key_says_what_to_do(monkeypatch):
    class NoKey:
        gemini_api_key = None
        gemini_models = "model-a"

    get_llm.cache_clear()
    monkeypatch.setattr(llm_module, "get_settings", lambda: NoKey())

    with pytest.raises(LlmError, match="GEMINI_API_KEY"):
        get_llm()
    get_llm.cache_clear()
