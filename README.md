# Vitext — AI-Powered Lecture → Visual Content Pipeline

Two output modes from the same project:

1. **Lecture Webpage Generator** (`lecture_webpage_generator/`) — Streamlit interactive pages from JSON payloads
2. **Vitext Manim Pipeline** (`vitext/`) — Animated explainer videos via a multi-agent Manim architecture

---

## 1. Lecture Webpage Generator

A Hybrid Template Engine where the AI **never writes code** — it outputs JSON,
and a pre-built renderer turns it into interactive pages (quizzes, graphs,
algorithm visualizers). Supports 6 categories: Coding, Algorithms, Poetry,
Mathematics, Science, Engineering.

```bash
cd lecture_webpage_generator
pip install -r requirements.txt
streamlit run app.py
```

See [`lecture_webpage_generator/README.md`](lecture_webpage_generator/README.md) for full details.

---

## 2. Vitext Manim Pipeline (NEW)

A **chunked, multi-modal, parallelized** architecture for generating
polished Manim-animated math/science videos from transcripts.

### Architecture

```
Transcript → Script Agent → [Cache → Code Agent → Render → Critic] × N → Assembly → .mp4
```

| Agent | Role |
|---|---|
| **Script Agent** | Breaks transcript into 3–8 atomic scene chunks |
| **Code Agent** | Generates Manim code per chunk using a Brand Library (no raw Manim) |
| **Critic Agent** | Vision model reviews rendered frames for overlaps, contrast, etc. |
| **Assembly Agent** | FFmpeg stitches all scenes with crossfade transitions |
| **Scene Cache** | SQLite + sentence-transformer embeddings for reusing past renders |

### Quick Start

```bash
pip install -r vitext/requirements.txt

# Also need Manim and FFmpeg installed:
# brew install ffmpeg   (macOS)
# pip install manim

export GOOGLE_API_KEY="your-gemini-api-key"

python -c "
from vitext.orchestrator import PipelineOrchestrator
orch = PipelineOrchestrator()
result = orch.run_sync('Explain the chain rule in calculus')
print(f'Video: {result.final_result.output_path}')
"
```

### Key Design Decisions

- **Brand Library over raw Manim**: The Code Agent imports from `vitext.brand_library` — pre-styled wrappers (`BrandTitle`, `BrandAxes`, `BrandFormula`) that enforce a cohesive dark-theme aesthetic. This prevents style drift.
- **No LangGraph**: Uses plain `asyncio.gather()` + semaphores for parallel scene processing. Lighter weight, no extra dependency.
- **Local caching**: SQLite + `sentence-transformers` (all-MiniLM-L6-v2). No cloud vector DB needed.
- **Gemini for all agents**: Script, Code, and Critic agents all use Gemini 2.5 Flash by default.
