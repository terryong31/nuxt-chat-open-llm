# 0001 — Run the inference server natively, no containers

Accepted · 2026-08-01

## Context

- MLX targets Metal. Linux containers on macOS get no Metal device.
- `mlx-lm` declares `mlx` under a `sys_platform == 'darwin'` marker, so
  `uv sync` on Linux **exits 0 having installed no mlx at all**. The failure
  lands at import, not at build — a container that builds green still can't run.
- The deployment target is one MacBook, reached over a tunnel.

## Decision

`uv run llm-server` on the host. No Dockerfile, no Compose.

## Rejected

| Option | Why not |
| --- | --- |
| Linux container with MLX | No Metal device to run on |
| Apple `container` CLI | Linux guests in lightweight VMs — same outcome |
| Swap to vLLM or llama.cpp, containerize that | Works, but changes what is being measured. The experiment is Mamba on Apple Silicon |
| Compose the frontend against a host-run server | Solves nothing; the frontend deploys to Vercel ([0002](0002-host-the-frontend-on-vercel.md)) |

## Consequences

- Reproducibility comes from `uv.lock` + `.python-version`, not an image.
- CI runs on macOS arm64 runners. `app.py` imports `MlxEngine` at module scope,
  so even fake-engine tests can't import on Linux.
- Availability is tied to one physical machine. The frontend has to degrade
  when it is off.
- Revisiting means writing one class against the `LLMEngine` protocol in
  `engine/base.py` and passing it to `create_app(engine=...)`. `api/` and
  `services/` don't move. That seam is the escape hatch this decision leans on.
