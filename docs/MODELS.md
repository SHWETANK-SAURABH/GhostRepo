# Models and hardware

Two separate things are involved:

- **Ollama** is the runtime. It downloads and serves models on your machine.
- **The model** is the open-weight network that writes the analysis. Each has its own license.

GhostRepo works without either. Verified findings, plans, README drafts and patches use no model.

## Default: `gemma3:4b`

This is the default because it is the model GhostRepo was actually tested with.

| | |
| --- | --- |
| Install | `ollama pull gemma3:4b` |
| Download size | 3.3 GB |
| Parameters | 4.3 billion, Q4_K_M quantization |
| License | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) |

The Gemma Terms of Use are not an OSI open-source license. The weights are openly available, but the terms include use restrictions. Read them before using the model in your own product. To see the exact license text of your installed copy, run `ollama show gemma3:4b --license`.

## Alternative: Qwen3

Qwen3 models are published under Apache-2.0, which is more permissive. Check the [Ollama library page](https://ollama.com/library/qwen3) for available sizes and confirm the license of the tag you choose.

```sh
ollama pull qwen3:<tag>
```

Then enter that name in **Settings → Model**. Qwen3 has **not** been tested with GhostRepo. The reply parser removes reasoning tags and validates output the same way for any model, so it should work, but the Settings page and report will show you if it does not.

## Using another model

Any Ollama model can be tried by entering its name in Settings. Models differ in how well they follow a JSON schema, so GhostRepo validates each reply:

1. It requests output matching a simplified JSON schema.
2. If Ollama refuses, it falls back to JSON mode.
3. It validates the reply and retries once if the reply is invalid.
4. If the reply is still invalid, it keeps the deterministic results, shows a warning and offers a retry.

To test a model against the validation pipeline:

```sh
cd backend
GHOSTREPO_TEST_MODEL=<name> .venv/bin/python -m pytest -m ollama
```

## Hardware

These are rough starting points, not measurements. Speed depends heavily on your GPU.

| Model size | Free memory (RAM or VRAM) | Notes |
| --- | --- | --- |
| Around 4B parameters | 6 to 8 GB | Usable on many laptops; a GPU helps a lot |
| Around 8B parameters | 10 to 12 GB | |
| Larger | 16 GB or more | Usually needs a GPU to be comfortable |

GhostRepo requests an 8,192-token context window (`GHOSTREPO_AI_CONTEXT_TOKENS`). Raising it uses more memory.

The default model timeout is 300 seconds (`GHOSTREPO_AI_TIMEOUT_SECONDS`). Raise it on slower hardware.

## Working offline

After dependencies and a model are downloaded, GhostRepo needs no internet connection. Ollama itself checks for updates when it has a connection; that is separate from GhostRepo.

## Endpoint restrictions

Evidence may only be sent to hosts in `GHOSTREPO_OLLAMA_ALLOWED_HOSTS`. By default these are local names. Add another host only if you control it, since repository evidence will be sent there.
