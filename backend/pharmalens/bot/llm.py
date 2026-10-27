"""Model adapters for the DrugDen agent: Gemini first, Groq as fallback, behind one tool-calling interface.

Conversation format (provider-neutral): a list of turns
    {"role": "user", "text": ...}
    {"role": "assistant", "text": ..., "calls": [{"id", "name", "args"}], "raw": <provider content>}
    {"role": "tool", "id": ..., "name": ..., "result": <json-serialisable>}
"""
import json
import logging
import os
import time

import httpx

log = logging.getLogger("drugden.llm")
# free-tier quota differs per model and key: tried in order (gemini-2.5-flash had no free quota on this key)
GEMINI_MODELS = [m.strip() for m in os.getenv("DRUGDEN_GEMINI_MODELS", "gemini-3-flash-preview,gemini-2.5-flash-lite").split(",") if m.strip()]
GROQ_MODEL = os.getenv("DRUGDEN_GROQ_MODEL", "openai/gpt-oss-120b")


class LLMError(RuntimeError):
    pass


def _gemini(system: str, turns: list[dict], tools: list[dict], model: str) -> dict:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY not set")
    contents = []
    for t in turns:
        if t["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": t["text"]}]})
        elif t["role"] == "assistant":
            # echo the model's own content back unchanged (it carries thought signatures for tool calls)
            contents.append(t.get("raw") if t.get("provider") == "gemini" and t.get("raw")
                            else {"role": "model", "parts": [{"text": t.get("text") or ""}] +
                                  [{"functionCall": {"name": c["name"], "args": c["args"]}} for c in t.get("calls", [])]})
        elif t["role"] == "tool":
            contents.append({"role": "user", "parts": [{"functionResponse": {"name": t["name"], "response": {"result": t["result"]}}}]})
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
            "tools": [{"functionDeclarations": [{"name": x["name"], "description": x["description"], "parameters": x["parameters"]} for x in tools]}],
            "generationConfig": {"temperature": 0.2}}
    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                   params={"key": key}, json=body, timeout=90)
    if r.status_code != 200:
        raise LLMError(f"gemini {r.status_code}: {r.text[:200]}")
    cand = (r.json().get("candidates") or [{}])[0]
    content = cand.get("content") or {"role": "model", "parts": []}
    parts = content.get("parts") or []
    text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
    calls = [{"id": f"g{i}", "name": p["functionCall"]["name"], "args": p["functionCall"].get("args") or {}}
             for i, p in enumerate(parts) if "functionCall" in p]
    if not text and not calls:
        raise LLMError(f"gemini returned nothing (finish={cand.get('finishReason')})")
    return {"role": "assistant", "text": text, "calls": calls, "raw": content, "provider": "gemini"}


def _groq(system: str, turns: list[dict], tools: list[dict]) -> dict:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY not set")
    msgs = [{"role": "system", "content": system}]
    for t in turns:
        if t["role"] == "user":
            msgs.append({"role": "user", "content": t["text"]})
        elif t["role"] == "assistant":
            m = {"role": "assistant", "content": t.get("text") or ""}
            if t.get("calls"):
                m["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                                   for c in t["calls"]]
            msgs.append(m)
        elif t["role"] == "tool":
            msgs.append({"role": "tool", "tool_call_id": t["id"], "content": json.dumps(t["result"], default=str)[:20000]})
    body = {"model": GROQ_MODEL, "messages": msgs, "temperature": 0.2,
            "tools": [{"type": "function", "function": {"name": x["name"], "description": x["description"], "parameters": x["parameters"]}} for x in tools]}
    for attempt in range(3):
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=90)
        if r.status_code != 429:
            break
        # per-minute token limit on the free tier: wait it out rather than fail
        time.sleep(min(30, float(r.headers.get("retry-after") or 12)))
    if r.status_code != 200:
        raise LLMError(f"groq {r.status_code}: {r.text[:200]}")
    m = r.json()["choices"][0]["message"]
    calls = [{"id": c["id"], "name": c["function"]["name"], "args": json.loads(c["function"].get("arguments") or "{}")}
             for c in (m.get("tool_calls") or [])]
    return {"role": "assistant", "text": m.get("content") or "", "calls": calls, "provider": "groq"}


def complete(system: str, turns: list[dict], tools: list[dict]) -> dict:
    """One model step. Gemini first; any failure (quota, outage) falls back to Groq for this step."""
    errors = []
    steps = [lambda m=m: _gemini(system, turns, tools, m) for m in GEMINI_MODELS] + [lambda: _groq(system, turns, tools)]
    for fn in steps:
        try:
            return fn()
        except (LLMError, httpx.HTTPError, KeyError, ValueError) as e:
            errors.append(str(e)[:160])
            log.warning("llm step failed: %s", e)
    raise LLMError(" | ".join(errors))
