"""LLM Interface with LiteLLM, tool calling, fallback resilience,
OpenUI structured parsing, and strict no-emoji enforcement.
"""

import json
import os
import re
from typing import Dict, Any, List, Optional
import litellm

from src.config import settings

# Configure API credentials in environment for LiteLLM
if settings.GROQ_API_KEY:
    os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY
if settings.GEMINI_API_KEY:
    os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY
if settings.OPEN_ROUTER_API_KEY:
    os.environ["OPENROUTER_API_KEY"] = settings.OPEN_ROUTER_API_KEY

# Regex pattern matching emoji and pictographic symbols
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
    "]+",
    flags=re.UNICODE
)


def strip_emojis(text: str) -> str:
    """Removes all emoji symbols to strictly uphold engineering standards."""
    if not text:
        return ""
    cleaned = _EMOJI_PATTERN.sub("", text)
    # Remove redundant whitespace left by removed emojis
    return re.sub(r"[ \t]{2,}", " ", cleaned)


from src.observability.langfuse_tracer import record_llm_generation


def get_models_for_task(task: str) -> List[str]:
    """
    Returns an ordered cascade of models tailored to the specific agent task:
    - 'planner': fast, reliable tool/function calling (default: Nemotron 3.5 Lightning)
    - 'reasoning': analytical deduction, logic & conflict detection (default: Nemotron 3 Nano Omni)
    - 'synthesis': 1M context, rich markdown, citations & OpenUI JSON (default: MiniMax M3.1 Flash)
    - 'general': primary model with full fallback sequence
    """
    if task == "planner":
        candidates = [
            settings.MODEL_TOOL_PLANNER,
            settings.MODEL_SYNTHESIZER,
            settings.MODEL_REASONER,
            settings.MODEL_SAFETY_NET,
            settings.PRIMARY_MODEL,
        ]
    elif task == "reasoning":
        candidates = [
            settings.MODEL_REASONER,
            settings.MODEL_TOOL_PLANNER,
            settings.MODEL_SYNTHESIZER,
            settings.MODEL_SAFETY_NET,
            settings.PRIMARY_MODEL,
        ]
    elif task == "synthesis":
        candidates = [
            settings.MODEL_SYNTHESIZER,
            settings.MODEL_TOOL_PLANNER,
            settings.MODEL_REASONER,
            settings.MODEL_SAFETY_NET,
            settings.PRIMARY_MODEL,
        ]
    else:
        candidates = [
            settings.PRIMARY_MODEL,
            settings.MODEL_TOOL_PLANNER,
            settings.MODEL_SYNTHESIZER,
            settings.MODEL_REASONER,
            settings.MODEL_SAFETY_NET,
        ]

    ordered: List[str] = []
    seen = set()
    for m in candidates:
        if m and m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


async def call_llm(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    task: str = "general",
    temperature: float = 0.0,
    max_tokens: int = 4096
) -> Dict[str, Any]:
    """
    Invokes a task-specialized model with tool-calling capabilities.
    Falls back gracefully through an ordered cascade of alternative models on 429s or failures.
    Traced end-to-end via Langfuse generation observations.
    """
    models_to_try = get_models_for_task(task)
    primary_task_model = models_to_try[0]

    model_params = {
        "task": task,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tools_count": len(tools) if tools else 0,
        "candidate_models": models_to_try
    }

    async with record_llm_generation(
        name=f"llm:{task}:{primary_task_model.split('/')[-1]}",
        model=primary_task_model,
        messages=messages,
        model_parameters=model_params
    ) as gen:
        last_error: Optional[Exception] = None

        for model_name in models_to_try:
            for attempt in range(2):
                try:
                    kwargs: Dict[str, Any] = {
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "timeout": 45.0
                    }
                    # Only include temperature for models that support it
                    if "gemini-3" not in model_name:
                        kwargs["temperature"] = temperature
                    if tools:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = "auto"

                    # Execute completion asynchronously
                    response = await litellm.acompletion(**kwargs)
                    choice = response.choices[0]
                    msg = choice.message

                    tool_calls = []
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            fn = tc.function
                            try:
                                args = json.loads(fn.arguments) if isinstance(fn.arguments, str) else fn.arguments
                            except Exception:
                                args = {"raw_arguments": fn.arguments}
                            tool_calls.append({
                                "id": getattr(tc, "id", f"call_{len(tool_calls)}"),
                                "name": fn.name,
                                "args": args
                            })

                    raw_content = getattr(msg, "content", "") or ""
                    cleaned_content = strip_emojis(raw_content)

                    # Capture token usage for Langfuse cost and latency analytics
                    usage = getattr(response, "usage", None)
                    usage_dict = None
                    if usage:
                        usage_dict = {
                            "input": getattr(usage, "prompt_tokens", 0) or 0,
                            "output": getattr(usage, "completion_tokens", 0) or 0,
                            "total": getattr(usage, "total_tokens", 0) or 0
                        }

                    gen.update(
                        model=model_name,
                        output={"content": cleaned_content, "tool_calls": tool_calls},
                        usage_details=usage_dict,
                        metadata={
                            "task": task,
                            "attempts": attempt + 1,
                            "is_fallback": model_name != primary_task_model,
                            "model_used": model_name
                        }
                    )

                    return {
                        "model_used": model_name,
                        "task": task,
                        "content": cleaned_content,
                        "tool_calls": tool_calls
                    }

                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    # If rate limited (429) or not found (404), immediately try next model in cascade
                    if "429" in err_str or "rate" in err_str or "404" in err_str or "not found" in err_str:
                        break
                    # Transient server overload: backoff and retry once
                    if attempt == 0 and ("503" in err_str or "high demand" in err_str or "timeout" in err_str):
                        import asyncio
                        await asyncio.sleep(1.5)
                        continue
                    break

        gen.update(level="ERROR", status_message=str(last_error))
        raise RuntimeError(f"All LLM invocation attempts for task '{task}' failed. Last error: {str(last_error)}")


def parse_openui_response(raw_text: str) -> Dict[str, Any]:
    """
    Parses and validates structured agent output conforming to OpenUI JSON specification.
    Recovers narrative and citations even if model wraps output in markdown code blocks.
    """
    cleaned = strip_emojis(raw_text).strip()

    # Attempt to extract JSON from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    candidate_str = fence_match.group(1).strip() if fence_match else cleaned

    try:
        data = json.loads(candidate_str)
        if isinstance(data, dict):
            narrative = strip_emojis(str(data.get("narrative", "")))
            citations = data.get("citations", [])
            generative_ui = data.get("generative_ui")
            return {
                "narrative": narrative or cleaned,
                "citations": citations if isinstance(citations, list) else [],
                "generative_ui": generative_ui if isinstance(generative_ui, dict) else None
            }
    except Exception:
        pass

    # Fallback: Extract inline citations via regex if JSON parsing is unavailable
    citation_regex = re.compile(r"\[(INS-[A-Za-z0-9-]+|MNT-[A-Za-z0-9-]+|SR-[0-9]+|RC-[0-9]+|CTX-[A-Za-z0-9-]+|SOP-[A-Za-z0-9-]+|NOTE-[0-9]+)\]")
    found_refs = list(set(citation_regex.findall(cleaned)))
    extracted_citations = [
        {"id": ref, "source_type": "extracted_reference", "reference": ref}
        for ref in found_refs
    ]

    return {
        "narrative": cleaned,
        "citations": extracted_citations,
        "generative_ui": None
    }
