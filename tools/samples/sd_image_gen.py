#!/usr/bin/env python3
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# --- Server config ---
SDCPP_BASE_URL = "http://127.0.0.1:1234"

# --- Generation defaults (Anima 2B v1.0 turbo) ---
WIDTH = 512
HEIGHT = 1024
NEGATIVE_PROMPT = "worst quality, low quality, score_1, score_2, score_3, oversaturated, jpeg artifacts, logo, watermark, bad anatomy, (bad hands:1.5), missing finger, extra digits, fewer digits, disfigured, mutation, 4 fingers, 6 fingers, censored"
STEPS = 8
CFG_SCALE = 1.0
SAMPLER = "euler"
SCHEDULER = "simple"
SEED = -1
BATCH_COUNT = 1
OUTPUT_FORMAT = "png"
OUTPUT_COMPRESSION = 100
POLL_INTERVAL = 0.5
TIMEOUT = 300


def _json_request(method: str, url: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.reason}")
    except URLError as e:
        raise RuntimeError(f"Connection error: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Bad JSON response: {e}")


def get_available_loras() -> list[dict]:
    """Queries available LoRAs directly from /sdcpp/v1/capabilities."""
    try:
        caps = _json_request("GET", f"{SDCPP_BASE_URL}/sdcpp/v1/capabilities")
        if isinstance(caps, dict) and "loras" in caps:
            return caps.get("loras", [])
    except Exception:
        pass
    return []


def resolve_to_server_path(raw_identifier: str, server_loras: list[dict]) -> str:
    """Ensures the value matches the exact 'path' expected by sd.cpp."""
    for item in server_loras:
        p = item.get("path", "")
        n = item.get("name", "")
        if raw_identifier in (p, n) or raw_identifier == p.rsplit(".", 1)[0]:
            return p
    return raw_identifier


def main():
    data = json.load(sys.stdin)

    # --- Mode 1: Query available LoRAs ---
    if data.get("list_loras") or data.get("action") == "list_loras":
        loras = get_available_loras()
        print(json.dumps({"loras": loras, "count": len(loras)}))
        return

    # --- Mode 2: Generate Image ---
    prompt = data.get("prompt", "")
    negative_prompt = data.get("negative_prompt", NEGATIVE_PROMPT)

    if not prompt.strip():
        print(json.dumps({"error": "prompt is required"}))
        return

    width = int(data["width"]) if "width" in data else WIDTH
    height = int(data["height"]) if "height" in data else HEIGHT

    # Fetch available LoRAs to validate paths against server capabilities
    server_loras = get_available_loras()

    lora_input = data.get("lora", data.get("loras", []))
    formatted_lora = []

    if isinstance(lora_input, list):
        for item in lora_input:
            if isinstance(item, str):
                formatted_lora.append({
                    "path": resolve_to_server_path(item, server_loras),
                    "multiplier": 1.0,
                })
            elif isinstance(item, dict):
                raw_path = item.get("path") or item.get("name")
                if not raw_path:
                    continue
                entry = {
                    "path": resolve_to_server_path(str(raw_path), server_loras),
                    "multiplier": float(item.get("multiplier", 1.0)),
                }
                if "is_high_noise" in item:
                    entry["is_high_noise"] = bool(item["is_high_noise"])
                formatted_lora.append(entry)

    # Request body strictly compliant with /sdcpp/v1/img_gen
    request_body = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "seed": SEED,
        "batch_count": BATCH_COUNT,
        "sample_params": {
            "scheduler": SCHEDULER,
            "sample_method": SAMPLER,
            "sample_steps": STEPS,
            "guidance": {
                "txt_cfg": CFG_SCALE,
            },
        },
        "lora": formatted_lora,
        "output_format": OUTPUT_FORMAT,
        "output_compression": OUTPUT_COMPRESSION,
    }

    try:
        submit = _json_request("POST", f"{SDCPP_BASE_URL}/sdcpp/v1/img_gen", request_body)
    except RuntimeError as e:
        print(json.dumps({"error": f"Submission failed: {e}"}))
        return

    job_id = submit.get("id")
    if not job_id:
        print(json.dumps({"error": "No job id in response"}))
        return

    deadline = time.time() + TIMEOUT
    poll_url = f"{SDCPP_BASE_URL}/sdcpp/v1/jobs/{job_id}"

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            status = _json_request("GET", poll_url)
        except RuntimeError as e:
            print(json.dumps({"error": f"Poll failed: {e}"}))
            return

        state = status.get("status")
        if state == "completed":
            result = status.get("result") or {}
            images = result.get("images") or []
            if not images:
                print(json.dumps({"error": "Job completed but no images in result"}))
                return
            img = images[0]
            b64 = img.get("b64_json")
            if not b64:
                print(json.dumps({"error": "Image result missing b64_json"}))
                return
            fmt = result.get("output_format", OUTPUT_FORMAT)
            mime = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}.get(fmt, "image/png")

            lora_desc = f", lora: {[l['path'] for l in formatted_lora]}" if formatted_lora else ""
            print(json.dumps({
                "image": {
                    "base64": b64,
                    "mime": mime,
                    "description": f"Generated image ({width}x{height}, {SAMPLER}, {STEPS} steps{lora_desc})",
                },
            }))
            return

        if state in ("failed", "cancelled"):
            err = status.get("error") or {}
            msg = err.get("message") or state
            print(json.dumps({"error": f"Job {state}: {msg}"}))
            return

    print(json.dumps({"error": f"Job did not complete within {TIMEOUT}s"}))


if __name__ == "__main__":
    main()
