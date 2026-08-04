# Link check report — final document

Access date check run: 2026-08-03
Sources in §20: 239 (238 with an HTTP URL; [236] is an internal relative link to the prior pass and is not HTTP-checked)
Main-doc HTTP URLs checked: 238
OK (HTTP 200): 227
Fail/blocked: 11 — all `openai.com` / `help.openai.com` bot-blocks

Two `github.com` URLs ([11], [48]) returned HTTP 429 on the concurrent pass and 200 on a serial retry; they are counted OK.
The three CaMeL sources added to §20.3 ([237] arXiv 2503.18813, [238] arXiv 2506.08837, [239] arXiv 2601.09923) each return HTTP 200.

## Failures / blocks
- `FAIL` https://help.openai.com/en/articles/6825453-chatgpt-release-notes — HTTP Error 403: Forbidden
- `FAIL` https://help.openai.com/en/articles/8590148-memory-in-chatgpt-remembering-what-you-chat-about — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/browsecomp — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/computer-using-agent/ — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/deep-research-system-card/ — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/gdpval/ — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/gpt-5-1-codex-max/ — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/introducing-agentkit/ — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/separating-signal-from-noise-coding-evaluations/ — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/swe-lancer/ — HTTP Error 403: Forbidden
- `FAIL` https://openai.com/index/unrolling-the-codex-agent-loop/ — HTTP Error 403: Forbidden
