#!/usr/bin/env python3
import json
import sys
import time
import base64
from urllib.request import Request, urlopen
from urllib.error import URLError

# --- Server config ---
SDCPP_BASE_URL = "http://127.0.0.1:1234"

# --- Generation defaults (Anima 2B v1.0 turbo) ---
WIDTH = 1024
HEIGHT = 1024
NEGATIVE_PROMPT = "worst quality, low quality, score_1, score_2, score_3, artist name, blurry, jpeg artifacts, chromatic aberration"
STEPS = 10
CFG_SCALE = 1.0
SAMPLER = "euler"
SCHEDULER = "discrete"
SEED = -1
BATCH_COUNT = 1
OUTPUT_FORMAT = "png"
OUTPUT_COMPRESSION = 100
POLL_INTERVAL = 0.5
TIMEOUT = 300


def _json_request(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        raise RuntimeError(f"Server error: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Bad JSON response: {e}")


def main():
    data = json.load(sys.stdin)
    prompt = data.get("prompt", "")
    negative_prompt = data.get("negative_prompt", NEGATIVE_PROMPT)

    if not prompt.strip():
        print(json.dumps({"error": "prompt is required"}))
        return

    width = int(data["width"]) if "width" in data else WIDTH
    height = int(data["height"]) if "height" in data else HEIGHT

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
            print(json.dumps({
                "image": {
                    "base64": b64,
                    "mime": mime,
                    "description": f"Generated image ({width}x{height}, {SAMPLER}, {STEPS} steps)",
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
