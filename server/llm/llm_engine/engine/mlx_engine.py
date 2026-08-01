"""The MLX runtime, wrapped so no other module imports mlx.

The interesting problem here is that `stream_generate` is a *blocking*
generator and the server is asyncio. Bridging the two without either wedging
the event loop or letting a disconnected client leak a busy worker is most of
this file.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import asynccontextmanager, suppress

# pyrefly: ignore [missing-import]
import mlx.core as mx

# pyrefly: ignore [missing-import]
from mlx_lm import load, stream_generate

# pyrefly: ignore [missing-import]
from mlx_lm.sample_utils import make_logits_processors, make_sampler

from ..config import Settings
from ..errors import EngineBusy, EngineNotReady
from .base import (
    Completed,
    Delta,
    GenerationParams,
    Message,
    StreamEvent,
    ToolCalls,
    ToolSpec,
    Usage,
)
from .prompts import build_prompt
from .toolcalls import ToolCallSplitter

log = logging.getLogger(__name__)

# Sentinel pushed onto the queue by the worker's `finally`, so the consumer can
# tell "generation is over" from "no tokens yet".
_STREAM_END = object()

# How often a blocked worker thread re-checks whether its client went away.
# Only reached when the consumer is applying backpressure.
_EMIT_POLL_S = 0.1


def _reconcile_eos_tokens(tokenizer, extra: Sequence[str]) -> None:
    """Make sure the tokenizer's own EOS actually stops generation.

    mlx_lm builds its stop set from `config.json`'s `eos_token_id` and lets
    that override whatever the tokenizer declares. Community conversions get
    this wrong often enough to matter -- this checkpoint's config.json says 0
    (`<unk>`) while `</s>` is 2 -- and the failure is quiet and awful: nothing
    ever matches the stop set, so the model emits a literal "</s>" as text and
    keeps talking straight through the end of its turn into a hallucinated
    next one. Every reply runs to max_tokens.

    Union rather than replace, so a checkpoint with several legitimate stop
    tokens keeps all of them.
    """
    declared = getattr(tokenizer, "eos_token_id", None)
    if declared is not None and declared not in tokenizer.eos_token_ids:
        log.warning(
            "stop tokens %s from config.json exclude the tokenizer's own EOS "
            "%r (id %s); adding it, otherwise generation never terminates",
            sorted(tokenizer.eos_token_ids),
            tokenizer.eos_token,
            declared,
        )
        tokenizer.eos_token_ids = set(tokenizer.eos_token_ids) | {declared}

    for token in extra:
        tokenizer.add_eos_token(token)


class MlxEngine:
    """Single-process, single-concurrency MLX inference.

    Implements `LLMEngine`. One instance owns the weights for the lifetime of
    the process; it is created in the app factory and started in the lifespan.
    """

    supports_images = False
    # The checkpoint emits Mistral `[TOOL_CALLS]` when the tools block sits in
    # the right place. Compliance is uneven -- see server/llm/CLAUDE.md -- but
    # the protocol is implemented, so a tool-tuned checkpoint works unchanged.
    supports_tools = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.model_id = settings.model_id
        self._model = None
        self._tokenizer = None

        # MLX generation is not thread-safe, and each concurrent run allocates
        # its own state on top of the weights. A single-worker executor is the
        # hard guarantee that two generations never overlap: it holds no matter
        # how a request task is cancelled, whereas an asyncio lock alone does
        # not, because cancelling a task does not kill the thread it started.
        # The lock below governs *admission* to that worker, not exclusion.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
        self._lock = asyncio.Lock()
        self._waiting = 0

    # -- lifecycle ----------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    async def start(self) -> None:
        mx.set_cache_limit(self._settings.cache_limit_mb * 1024**2)
        log.info("loading %s", self.model_id)

        # Loading runs on the worker rather than inline so the event loop stays
        # responsive to signals -- otherwise Ctrl-C is swallowed for the entire
        # multi-GB read and the process has to be killed.
        loop = asyncio.get_running_loop()
        self._model, self._tokenizer = await loop.run_in_executor(
            self._worker, load, self.model_id
        )
        _reconcile_eos_tokens(self._tokenizer, self._settings.extra_eos_tokens)
        log.info(
            "loaded, %.2f GB resident, stop tokens %s",
            mx.get_active_memory() / 1024**3,
            sorted(self._tokenizer.eos_token_ids),
        )

    async def stop(self) -> None:
        self._model = None
        self._tokenizer = None
        # wait=True: an in-flight generation still holds references to the
        # weights, so tearing down before it returns would free them underneath
        # a live thread.
        self._worker.shutdown(wait=True)
        mx.clear_cache()

    def stats(self) -> dict[str, float]:
        return {
            "active_gb": round(mx.get_active_memory() / 1024**3, 2),
            "cache_gb": round(mx.get_cache_memory() / 1024**3, 2),
            "peak_gb": round(mx.get_peak_memory() / 1024**3, 2),
            "queued": float(self._waiting),
        }

    # -- admission ----------------------------------------------------------

    @asynccontextmanager
    async def _admit(self) -> AsyncIterator[None]:
        """Serialize generations, but fail fast instead of queueing forever.

        Without this, a burst of traffic produces a queue of clients that have
        already timed out, and the GPU spends its time generating replies that
        nobody is listening for.
        """
        if self._waiting >= self._settings.max_queue_depth:
            raise EngineBusy(
                f"{self._waiting} requests already queued; try again shortly"
            )

        self._waiting += 1
        try:
            try:
                await asyncio.wait_for(
                    self._lock.acquire(), self._settings.queue_timeout_s
                )
            except TimeoutError as exc:
                raise EngineBusy(
                    f"timed out after {self._settings.queue_timeout_s:g}s "
                    "waiting for the model"
                ) from exc
            try:
                yield
            finally:
                self._lock.release()
        finally:
            self._waiting -= 1

    # -- generation ---------------------------------------------------------

    async def stream_chat(
        self,
        messages: Sequence[Message],
        params: GenerationParams,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[StreamEvent]:
        if self._model is None or self._tokenizer is None:
            raise EngineNotReady("model is not loaded")

        prompt = build_prompt(self._tokenizer, messages, tools)

        async with self._admit():
            loop = asyncio.get_running_loop()
            # Bounded: a slow client should throttle generation rather than let
            # tokens accumulate in memory ahead of it.
            queue: asyncio.Queue[object] = asyncio.Queue(
                maxsize=self._settings.stream_queue_size
            )
            cancel = threading.Event()

            def emit(item: object) -> bool:
                """Hand an item to the loop, blocking this thread if the queue
                is full. Returns False once the consumer has gone away.

                Polled rather than a bare `.result()`: if the client
                disconnects while the queue is full, nothing will ever drain it
                and an unpolled wait would pin the only worker thread forever.
                """
                future = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
                while not cancel.is_set():
                    try:
                        future.result(timeout=_EMIT_POLL_S)
                        return True
                    except FutureTimeout:
                        continue
                future.cancel()
                return False

            def generate() -> None:
                try:
                    # Holds back text that could still be the start of a
                    # `[TOOL_CALLS]` marker, so a marker split across chunks
                    # never leaks into the visible answer.
                    splitter = ToolCallSplitter()
                    response = None
                    for response in stream_generate(
                        self._model,
                        self._tokenizer,
                        prompt=prompt,
                        max_tokens=params.max_tokens,
                        sampler=make_sampler(
                            temp=params.temperature,
                            top_p=params.top_p,
                        ),
                        logits_processors=make_logits_processors(
                            repetition_penalty=params.repetition_penalty,
                            repetition_context_size=params.repetition_context_size,
                        ),
                    ):
                        visible = splitter.feed(response.text)
                        if visible and not emit(Delta(visible)):
                            return

                    # A partial marker that never completed is ordinary text;
                    # releasing it here is what keeps it from being swallowed.
                    trailing, tool_calls = splitter.finish()
                    if trailing and not emit(Delta(trailing)):
                        return
                    if tool_calls and not emit(ToolCalls(tuple(tool_calls))):
                        return

                    if response is None:
                        # Nothing was generated at all (e.g. the very first
                        # token was EOS). Still terminate the stream properly.
                        emit(Completed("stop", Usage(0, 0)))
                        return

                    log.info(
                        "%d tokens @ %.1f tok/s, peak %.2f GB, finish=%s",
                        response.generation_tokens,
                        response.generation_tps,
                        response.peak_memory,
                        response.finish_reason,
                    )
                    emit(
                        Completed(
                            # OpenAI clients branch on this: langchain routes to
                            # the tool node only when it reads "tool_calls".
                            # mlx leaves its own value None if the loop ended
                            # without a stop token, meaning the cap was reached.
                            finish_reason="tool_calls"
                            if tool_calls
                            else (response.finish_reason or "length"),
                            usage=Usage(
                                prompt_tokens=response.prompt_tokens,
                                completion_tokens=response.generation_tokens,
                            ),
                        )
                    )
                except BaseException as exc:  # noqa: BLE001 - re-raised on the loop
                    # Handing the exception to the consumer keeps the traceback
                    # attached to the request that caused it, instead of losing
                    # it in a worker thread.
                    emit(exc)
                finally:
                    # Release this request's working set before the next one
                    # starts building its own.
                    mx.clear_cache()
                    emit(_STREAM_END)

            future = loop.run_in_executor(self._worker, generate)
            try:
                while True:
                    item = await queue.get()
                    if item is _STREAM_END:
                        break
                    if isinstance(item, BaseException):
                        raise item
                    yield item  # type: ignore[misc]
            finally:
                # Reached on client disconnect too: Starlette closes the
                # response generator, which closes this one, and the worker
                # notices the flag on its next emit. Best-effort join keeps the
                # common path tidy; correctness does not depend on it, because
                # the single-worker executor already serializes the next run
                # behind this thread.
                cancel.set()
                with suppress(Exception, asyncio.CancelledError):
                    await asyncio.shield(future)
