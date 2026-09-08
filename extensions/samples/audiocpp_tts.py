#!/usr/bin/env python3
"""Read a message aloud via an audio.cpp server's ``/v1/audio/speech``.

The audio.cpp HTTP adapter is OpenAI-compatible for TTS. We POST
``{"model", "input", ...}`` and take the response bytes back — ``audio/wav`` by
default — and **play them in the browser**. We never persist the clip as a message
attachment: an ``audio/*`` attachment is sent back to the model as ``input_audio``
on later turns, which would make the model re-hear its own reply.

Only ``text`` segments are spoken; reasoning and tool boundaries are skipped.
Optional ``text_pattern`` narrows what's spoken — a regex applied to the reply.
Capture groups read only the captured text, so ``"([^"]+)"`` speaks the quoted
phrases; empty reads the whole message.

**Auto-load.** The selected ``model`` is loaded on demand. Before speaking we check
``/v1/models``; if the id isn't registered yet we resolve its ``path``/``family``/
``task``/``mode`` from the model catalog embedded in the server's Web UI page, POST
``/v1/models/load`` with that payload, then speak. A model stays resident, so
subsequent runs skip the load. This surfaces a clear message instead of the raw
``unknown model id`` when a model can't be resolved or its files are missing.

**Model residency.** audio.cpp keeps every loaded model in VRAM (``max_loaded_models``
defaults to 0 = unlimited), so switching models can exhaust the GPU. We therefore
unload other loaded models before loading a new one — set ``unload_others`` to
``false`` to keep multiple models resident instead.

On stdin: the extension request envelope. On stdout: the extension result JSON.
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Leave a small margin below the JSON spec's subprocess timeout (default 300s) so
# a slow request errors cleanly rather than being killed mid-call.
_REQUEST_TIMEOUT = 280

_MIME_EXT = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/flac": "flac",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
}

# The Web UI page serialises the model catalog as struct entries with a fixed
# field order: family, path, task, mode, download_id.
_CATALOG_ENTRY_RE = re.compile(
    r'"family":"([^"]+)","path":"([^"]+)","task":"([^"]+)","mode":"([^"]+)","download_id":"([^"]+)"'
)


def _pick_filename(content_type: str) -> str:
    ext = _MIME_EXT.get(content_type, "wav")
    return f"reply.{ext}"


def _apply_pattern(text: str, pattern: str) -> str:
    """Extract the text to speak from ``text`` using ``pattern``.

    With capture groups the first (non-None) group is spoken — so ``"([^\"]+)"``
    reads just the quoted phrases. Without groups the whole match is spoken.
    Overlapping hits are joined by spaces. An empty result means nothing matched.
    """
    parts: list[str] = []
    for m in re.finditer(pattern, text):
        if m.groups():
            content = next((g for g in m.groups() if g is not None), m.group(0))
        else:
            content = m.group(0)
        parts.append(content)
    return " ".join(parts)


def _http_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[str, bytes]:
    """Make an HTTP request and return ``(content_type, body)``.

    Raises RuntimeError on transport errors, HTTP errors, and timeouts so the
    caller can surface a friendly message.
    """
    url = base_url + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            return content_type, resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()
        raise RuntimeError(f"audio.cpp_server responded {e.code}: {detail or e.reason}")
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None) or e
        raise RuntimeError(f"audio.cpp_server unreachable at {base_url}: {reason}")
    except TimeoutError:
        raise RuntimeError(f"audio.cpp_server timed out after {_REQUEST_TIMEOUT}s")
    except OSError as e:
        raise RuntimeError(f"audio.cpp request failed: {e}")


def _catalog_entry(html: str, model_id: str) -> tuple[str, str, str, str] | None:
    """Return ``(family, path, task, mode)`` for ``model_id`` from the catalog page."""
    for fam, path, task, mode, did in _CATALOG_ENTRY_RE.findall(html):
        if did == model_id:
            return fam, path, task, mode
    # Fallback: the server may reorder fields. Search a window around the id.
    idx = html.find(f'"download_id":"{model_id}"')
    if idx == -1:
        return None
    window = html[max(0, idx - 300) : idx + len(model_id) + 40]
    fam = re.search(r'"family":"([^"]+)"', window)
    path = re.search(r'"path":"([^"]+)"', window)
    task = re.search(r'"task":"([^"]+)"', window)
    mode = re.search(r'"mode":"([^"]+)"', window)
    if fam and path and task and mode:
        return fam.group(1), path.group(1), task.group(1), mode.group(1)
    return None


def _loaded_model_ids(base_url: str) -> list[str]:
    """Ids currently loaded on the server (unloaded models stay listed with loaded=false)."""
    _, raw = _http_json(base_url, "/v1/models")
    try:
        data = json.loads(raw).get("data", [])
    except (ValueError, AttributeError):
        return []
    return [m["id"] for m in data if m.get("loaded") and m.get("id")]


def _is_loaded(base_url: str, model_id: str) -> bool:
    return model_id in _loaded_model_ids(base_url)


def _unload_others(base_url: str, keep_id: str) -> None:
    """Unload every loaded model except ``keep_id`` to free VRAM before a switch.

    Uses ``/v1/models/unload`` which updates the ``loaded`` flag reliably — the
    batch ``/v1/tasks/unload_models`` endpoint silently no-ops on some servers.
    """
    for model_id in _loaded_model_ids(base_url):
        if model_id == keep_id:
            continue
        _http_json(base_url, "/v1/models/unload", "POST", {"id": model_id})


def _load_model(base_url: str, model_id: str) -> None:
    """Resolve the model's catalog entry and POST ``/v1/models/load``."""
    _, raw = _http_json(base_url, "/v1/ui/models-root")
    try:
        models_root = json.loads(raw)["models_root"]
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"audio.cpp_server did not report a models root: {e}")

    _, page = _http_json(base_url, "/")
    entry = _catalog_entry(page.decode("utf-8", "replace"), model_id)
    if entry is None:
        raise RuntimeError(f"audio.cpp_server does not know model '{model_id}'; install it or load it first")
    family, rel_path, task, mode = entry
    abs_path = os.path.normpath(os.path.join(os.path.dirname(models_root), rel_path))

    payload = {
        "id": model_id,
        "path": abs_path,
        "family": family,
        "task": task,
        "mode": mode,
        "load_options": {},
        "session_options": {},
    }
    ctype, raw = _http_json(base_url, "/v1/models/load", "POST", payload)
    if ctype == "application/json":
        result = json.loads(raw)
        if result.get("loaded") is not True:
            raise RuntimeError(f"audio.cpp_server failed to load '{model_id}': {result}")


def _ensure_loaded(base_url: str, model_id: str, unload_others: bool) -> None:
    if _is_loaded(base_url, model_id):
        return
    if unload_others:
        _unload_others(base_url, model_id)
    _load_model(base_url, model_id)


def _post_speech(base_url: str, body: dict) -> tuple[bytes, str]:
    """POST ``/v1/audio/speech`` and return ``(audio_bytes, content_type)``."""
    content_type, payload = _http_json(base_url, "/v1/audio/speech", "POST", body)
    if content_type == "application/json":
        try:
            parsed = json.loads(payload.decode("utf-8", "replace"))
        except (ValueError, UnicodeDecodeError):
            parsed = {}
        msg = parsed.get("error") or parsed.get("message") or payload[:200].decode("utf-8", "replace")
        if "unknown model id" in msg:
            msg += " — the audio.cpp server could not load this model"
        raise RuntimeError(f"audio.cpp_server returned JSON: {msg}")
    return payload, content_type


def main() -> None:
    req = json.load(sys.stdin)
    cfg = req.get("config", {}) or {}
    target = req.get("target", {}) or {}
    segments = target.get("segments") or []
    text = "".join(s.get("content", "") for s in segments if s.get("type") == "text").strip()
    if not text:
        text = (target.get("content") or "").strip()

    if not text:
        print(json.dumps({"status": "done", "logs": [{"level": "info", "message": "no text to speak"}]}))
        return

    text_pattern = (cfg.get("text_pattern") or "").strip()
    if text_pattern:
        try:
            text = _apply_pattern(text, text_pattern)
        except re.error as e:
            print(json.dumps({"status": "error", "error": f"audiocpp_tts: invalid text_pattern: {e}"}))
            return
        if not text:
            print(
                json.dumps(
                    {
                        "status": "done",
                        "logs": [{"level": "info", "message": f"no text matched pattern {text_pattern!r}"}],
                    }
                )
            )
            return

    base_url = (cfg.get("base_url") or "http://localhost:8081").rstrip("/")
    model = (cfg.get("model") or "").strip()
    if not model:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "audiocpp_tts: 'model' is required (pick one from the dropdown)",
                }
            )
        )
        return

    body = {"model": model, "input": text}

    voice = (cfg.get("voice") or "").strip()
    if voice:
        body["voice"] = voice

    max_tokens = cfg.get("max_tokens")
    if max_tokens is not None:
        try:
            mt = int(max_tokens)
            if mt > 0:
                body["max_tokens"] = mt
        except (TypeError, ValueError):
            pass

    seed = (cfg.get("seed") or "").strip()
    if seed:
        body["seed"] = seed

    try:
        _ensure_loaded(base_url, model, cfg.get("unload_others", True))
        audio, content_type = _post_speech(base_url, body)
    except RuntimeError as e:
        print(json.dumps({"status": "error", "error": str(e), "logs": [{"level": "error", "message": str(e)}]}))
        return

    if not audio:
        print(json.dumps({"status": "error", "error": "audio.cpp_server returned an empty audio body"}))
        return

    content_type = content_type or "audio/wav"
    print(
        json.dumps(
            {
                "status": "done",
                # Never persist the clip: an ``audio/*`` attachment is fed back to
                # the model as ``input_audio`` on later turns, so it must be played
                # in the browser only.
                "attach": False,
                "logs": [{"level": "success", "message": f"Spoke {len(text)} chars ({content_type})"}],
                "files": [
                    {
                        "name": _pick_filename(content_type),
                        "data": base64.b64encode(audio).decode("ascii"),
                        "mime": content_type,
                    }
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
