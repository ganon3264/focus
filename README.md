# Focus

A roleplaying thingy, kinda like SillyTavern, but opinionated and personal (and sloppy).

![Alt text](static/screenshot.png)

## Prerequisites

Python 3.11+
uv (optional, but recommended)
node.js (optional, for tests)

## How to use
```
git clone https://github.com/ganon3264/focus
cd focus
./start.sh
```

## Supported APIs

- Generic OAI compatible chat completion
- OpenRouter
 - Quantization, provider routing
 - Sticky routing by session ID
 - Claude caching support
- Deepseek
- Moonshot
- Google AI Studio
- Google Vertex AI

## Features

- Lightweight UI
- Easily themable
- Multimodal support as first class citizen
 - Attach images to prompt blocks, character cards, and personas; choose attachment's position within the card using a macro
- Basic toolcalling support
 - Generic OAI, Moonshot and Deepseek tested; Google not so much
- Prefill `reasoning_content` support for toolcalls and more complex presets
 - Actual support for sending `reasoning_content` back properly if model needs it (encrypted thinking not handled yet/if ever)
- Preset variables exposed in the UI with switches

## Why

SillyTavern has grown bloated, slow, and a potential security liability over the years, not to mention trying to add any functionality to it is a herculean effort.
After using it for a few years I've come to realization that I don't even use vast majority of its features, so I built my own thing with only the features that I use.

## Support

On "if I feel like it" basis, or "this affects me personally" depending on the issue.
Provided as is.
