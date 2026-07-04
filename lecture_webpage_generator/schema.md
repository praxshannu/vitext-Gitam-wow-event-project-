# Payload Schema

This is the contract between the **AI Processing Engine** (which only ever
outputs JSON — never Python/Streamlit code) and the **pre-built rendering
engine** in `app.py`. As long as a payload matches this schema, `app.py` can
render it, regardless of subject category. This separation is what makes
zero-shot reliability achievable: the AI can't break code syntax if it never
writes code.

## Top-level envelope

```json
{
  "subject_category": "coding | algorithms | poetry | mathematics | science | engineering",
  "page_title": "string",
  "content_blocks": [ /* see below */ ],
  "interactive_config": { /* see below, or null */ },
  "quiz_form": { /* see below */ }
}
```

## `content_blocks` (shared across all categories)

A list of blocks, rendered top to bottom. Each has a `type`:

| type | fields | used for |
|---|---|---|
| `text` | `value` | any prose |
| `latex_formula` | `value` (LaTeX string, no `$` delimiters) | math/science formulas |
| `image` | `url`, `caption` | standalone images |
| `text_with_links` | `segments`: list of `{text, url?}` | poetry/literature reference links — segments without a `url` render as plain text, segments with one become a markdown link |

## `interactive_config` (one per page, category-specific `type`)

Set to `null` if a category has no interactive widget (rare — poetry usually
relies on `text_with_links` instead).

### `code_practice` — Coding & Programming Languages
```json
{
  "type": "code_practice",
  "title": "string",
  "language": "python | javascript | c | ...",
  "reference_code": "string",
  "prompt": "string",
  "expected_keywords": ["for", "in"]
}
```
Renders a reference snippet plus a text-area practice area. **Deliberately
does not execute user-submitted code** — arbitrary code execution is a
security liability, so verification is keyword-based comparison against the
reference, not a sandboxed interpreter.

### `algorithm_visualizer` — Algorithms
```json
{
  "type": "algorithm_visualizer",
  "title": "string",
  "algorithm": "bubble_sort | binary_search | bfs | dijkstra",
  "input_type": "array | graph",
  "default_input": [5, 3, 8, 1, 9, 2]
}
```
For `input_type: "graph"`, `default_input` is an adjacency object, e.g.
`{"A": ["B", "C"]}` for `bfs`, or `{"A": {"B": 4}}` (weighted) for `dijkstra`.
The AI only names the algorithm and starting data — the actual step-by-step
execution is handled by pre-built, tested Python generators in `app.py`
(`ALGORITHMS` dict), so the AI can never produce an incorrect animation.
Adding a new algorithm means adding one generator function, not touching the
AI prompt's code-generation surface.

### `graph_2d` — Mathematics (functions)
```json
{
  "type": "graph_2d",
  "title": "string",
  "equation": "amplitude * np.sin(frequency * x + phase)",
  "x_range": [0, 10],
  "controls": [
    {"label": "Amplitude", "min": 0.1, "max": 5.0, "default": 1.0, "key": "amplitude"}
  ]
}
```
`equation` is evaluated through a restricted namespace (`math`/`numpy`
functions and the slider variables only — no builtins). See the security
note in `app.py`'s `safe_eval_formula`.

### `shape_2d` — Mathematics (geometry)
```json
{
  "type": "shape_2d",
  "title": "string",
  "shape": "circle | rectangle | triangle",
  "controls": [
    {"label": "Radius", "min": 0.5, "max": 10, "default": 3, "key": "radius"}
  ]
}
```
Control keys expected per shape: `circle` → `radius`; `rectangle` → `width`,
`height`; `triangle` → `side_a`, `side_b`, `side_c`.

### `media_gallery` — Hard Sciences
```json
{
  "type": "media_gallery",
  "title": "string",
  "images": [{"url": "string", "caption": "string"}],
  "simulation_note": "string"
}
```

### `numeric_calculator` — Engineering
```json
{
  "type": "numeric_calculator",
  "title": "string",
  "formula": "current * resistance",
  "output_label": "Voltage",
  "output_unit": "V",
  "inputs": [
    {"label": "Current", "unit": "A", "min": 0, "max": 20, "default": 2, "key": "current"}
  ]
}
```
Same restricted-eval mechanism as `graph_2d`.

## `quiz_form`

```json
{
  "mode": "instant_verify | tickbox | delayed_key | comprehensive",
  "title": "string",
  "pass_threshold": 0.7,
  "questions": [
    {
      "question": "string",
      "type": "single | multi",
      "options": ["string", "..."],
      "correct_indices": [1],
      "explanation": "string"
    }
  ]
}
```

- `correct_indices` is always a list — `[1]` for single-select, `[0, 2]` for
  multi-select checkboxes.
- `pass_threshold` is only read by `comprehensive` mode (default `0.7`).

### Quiz mode → behavior → typical category

| mode | behavior | spec requirement it satisfies |
|---|---|---|
| `instant_verify` | Per-question ✅/❌ the moment the form is submitted | Coding, Algorithms — "immediately score the quiz" |
| `tickbox` | Same immediate feedback, expected to lean on `type: "multi"` questions | Poetry, Science — "checkboxes for instant... verification" |
| `delayed_key` | Submitting just records answers; a separate "Reveal Answer Key" button shows the full key + score | Mathematics — "answer key revealed only upon final submission" |
| `comprehensive` | All questions validated together at the end into a pass/fail report against `pass_threshold` | Engineering — "absolute validation testing at the end" |

Both `instant_verify` and `tickbox` are handled by the same renderer in
`app.py` — the distinction in the spec is about question *style* (MCQ vs.
checkbox), not fundamentally different feedback timing, so they share code
rather than duplicating it.
