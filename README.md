<a id="readme-top"></a>

<div align="center">
  <h1>Local LLM & Web Search Agent</h1>
  <p><strong>High-Performance Apple Silicon Local AI Assistant powered by MLX, LangGraph, FastAPI, and Nuxt 4</strong></p>

  [![Python](https://img.shields.io/badge/Python-3.14+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-MLX_Metal-black.svg?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/ml-explore/mlx)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![LangGraph](https://img.shields.io/badge/LangGraph-ReAct_Agent-blueviolet.svg?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
  [![Nuxt 4](https://img.shields.io/badge/Nuxt-4.5+-00DC82.svg?style=for-the-badge&logo=nuxtdotjs&logoColor=white)](https://nuxt.com)
  [![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38B2AC.svg?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
</div>

---

## Overview

**Local LLM** is a full-stack, local AI assistant engineered for Apple Silicon Macs. It combines native **MLX GPU acceleration** with a **LangGraph ReAct agent loop**, live **DuckDuckGo web search and page fetching**, and a modern **Nuxt 4 + Nuxt UI** conversational interface with real-time SSE streaming.

---

## Key Features

- **Native Apple Silicon Acceleration**: Powered by `mlx-lm` for low-latency unified memory inference on Apple M-series chips.
- **Multi-Model Memory Preloading**:
  - **Qwen 3.5 9B (8-bit)**: Fast responsiveness (~45-50 tokens/sec).
  - **Qwen 3.8 27B (4-bit)**: Deep reasoning and complex coding (~7.7 tokens/sec at peak memory bandwidth).
  - Models are preloaded into Unified Memory on startup for instant (0.0s) model switching.
- **Dual Web Tools**:
  - `web_search`: Live DuckDuckGo web search with snippet aggregation.
  - `web_fetch`: Rich body text extraction via Trafilatura for full documentation pages and live data.
- **Deterministic Multi-Step ReAct Agent**:
  - Full support for parallel and sequential tool calling without tag leakage.
  - Guaranteed answer synthesis phase to prevent infinite search loops.
- **Reasoning Isolation & Thinking Budget**:
  - Thinking tokens are strictly isolated within collapsible thought accordions.
  - Zero thinking or tool tags bleed into the final markdown response.
- **Real-Time Telemetry & Metrics**:
  - Live hardware metrics: Generation speed (`tok/s`), Prompt prefill speed, Peak RAM usage, and elapsed execution time.
- **Modern Nuxt UI Interface**:
  - Dark and light themes, source cards with collapsible previews, markdown rendering with syntax highlighting, and responsive layout.

---

## Architecture

```mermaid
graph TD
    User([User Prompt]) --> Frontend[Nuxt 4 + Nuxt UI Chat App]
    Frontend -->|SSE POST /chat| Backend[FastAPI Backend Server]
    
    subgraph ModelManager [Unified Memory Model Manager]
        MM[In-Memory Model Cache]
        Qwen9B[(Qwen 3.5 9B 8-bit)]
        Qwen27B[(Qwen 3.8 27B 4-bit)]
        MM --> Qwen9B
        MM --> Qwen27B
    end
    
    Backend --> ModelManager
    Backend --> AgentEngine[LangGraph ReAct Agent Engine]
    
    subgraph AgentEngine [src/local_llm/agent]
        Think[Reasoning & Decision Pass]
        ToolDetect{Tool Invocation?}
        ToolsNode[Tools Execution Node]
        SynthPass[Guaranteed Synthesis Pass]
        
        Think --> ToolDetect
        ToolDetect -- Yes --> ToolsNode
        ToolsNode -->|web_search / web_fetch| ExtTools[DuckDuckGo & Trafilatura]
        ExtTools --> ToolsNode
        ToolsNode --> SynthPass
        ToolDetect -- No --> SynthPass
    end
    
    AgentEngine -->|Token Stream & Telemetry| Frontend
```

---

## Repository Structure

```text
local-llm/
├── src/                     # Backend Python application & config
│   ├── local_llm/           # Python FastAPI modular package
│   │   ├── core/            # Pydantic BaseSettings & configuration
│   │   ├── schemas/         # Request / Response DTO models
│   │   ├── models/          # ModelManager Unified Memory preloader
│   │   ├── agent/           # LangGraph ReAct agent & streaming engine
│   │   ├── tools/           # DuckDuckGo search & Trafilatura fetch tools
│   │   ├── api/             # Versioned API routes (/chat, /health)
│   │   └── main.py          # FastAPI application factory & lifespan
│   ├── main.py              # Backend entrypoint launcher
│   ├── pyproject.toml       # Backend Python dependencies (managed via uv)
│   ├── uv.lock              # Lockfile
│   ├── .python-version      # Python runtime pin
│   └── .env                 # Backend environment variables (HF_TOKEN, etc.)
├── chat-app/                # Frontend Nuxt 4 application & config
│   ├── app/                 # Chat UI pages, components & composables
│   ├── server/              # Server endpoints & database logic
│   ├── shared/utils/        # Model definitions and helpers
│   ├── package.json         # Frontend dependencies (managed via bun)
│   ├── bun.lock             # Lockfile
│   └── .env                 # Frontend environment variables (NUXT_SESSION_PASSWORD, etc.)
├── .gitignore
├── README.md
├── mise.toml                # Mise monorepo task runner configuration
├── CONTRIBUTING.md
└── AGENTS.md
```

---

## Getting Started

### Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4/M5 recommended, 16GB+ RAM).
- [mise](https://mise.jdx.dev/) for monorepo and runtime management.
- [uv](https://github.com/astral-sh/uv) for fast Python package management.
- [bun](https://bun.sh) for frontend package management.

---

### Quick Start with Mise (Recommended)

```bash
# 1. Configure backend environment
cp src/.env.example src/.env

# 2. Configure frontend environment
cp chat-app/.env.example chat-app/.env

# 3. Start everything concurrently
mise run dev:all
```

Or start components individually:
- **Backend only**: `mise run dev:be` (starts FastAPI on `http://127.0.0.1:8000`)
- **Frontend only**: `mise run dev:web` (starts Nuxt 4 on `http://localhost:3000`)

---

### Manual Setup

#### 1. Backend Setup

```bash
cd src
uv sync
cp .env.example .env
uv run main.py
```

#### 2. Frontend Setup

```bash
cd chat-app
bun install
cp .env.example .env
bun dev
```

Open `http://localhost:3000` in your browser.

---

## Configuration

### Backend (`src/.env`)
```env
# Optional: Hugging Face Token for fast model downloads
HF_TOKEN=hf_your_token_here

# Optional: Enable live reloading for backend development
RELOAD=false
```

### Frontend (`chat-app/.env`)
```env
# Password for nuxt-auth-utils (minimum 32 characters)
NUXT_SESSION_PASSWORD=your_session_secret_key_here

# Local LLM Backend API URL (Default: http://127.0.0.1:8000)
LOCAL_LLM_URL=http://127.0.0.1:8000
```

---

## Model Performance on Apple Silicon

| Model | Quantization | RAM Usage | Generation Speed (M5) |
| :--- | :--- | :--- | :--- |
| **Qwen 3.5 9B** | 8-bit | ~9.5 GB | **~45-50 tok/s** |
| **Qwen 3.8 27B** | 4-bit | ~15.0 GB | **~7.5-8.0 tok/s** |

---

## Contributing

Contributions are welcome! Please check out [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code style, development workflow, and pull request guidelines.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>