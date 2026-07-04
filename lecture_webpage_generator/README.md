# Automated Interactive Streamlit Webpage Generator

A working implementation of the Hybrid Template Engine, extended from the
math-only proof of concept to all six subject categories in the spec:
Coding, Algorithms, Poetry & Literature, Mathematics, Hard Sciences, and
Engineering.

**The core idea stays the same and is why this hits zero-shot reliability:**
the AI never writes Streamlit or Python code. It only ever outputs a JSON
object (schema in `schema.md`). One pre-built, pre-tested rendering engine
(`app.py`) turns that JSON into a full interactive page, for any of the six
categories. Since the AI's entire output surface is strings/numbers/arrays,
there's no code for it to get wrong.

## Files

| file | purpose |
|---|---|
| `app.py` | The rendering engine. Run this with Streamlit. |
| `schema.md` | The JSON contract between the AI and the renderer. |
| `ai_system_prompt.md` | System prompt to give an LLM so it acts as the "AI Processing Engine" — reads a transcript, classifies it, and outputs schema-valid JSON. |
| `sample_payloads/*.json` | One worked example per category, so you can see every interactive type and every quiz mode render without needing an API key. |
| `test_app.py` | Automated test that loads every sample, exercises every widget and button, and asserts no exceptions. Run it after any change to `app.py`. |
| `requirements.txt` | Dependencies. |

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

In the sidebar you can:
1. **Sample gallery** — browse the six pre-built examples with zero setup.
2. **Upload JSON payload** — drop in any JSON file matching `schema.md`.
3. **Generate from transcript** — paste a lecture transcript and your own
   Anthropic API key, and the app calls the model live using
   `ai_system_prompt.md`, then renders whatever JSON comes back.

Option 3 is the full pipeline described in the spec (transcript → classify →
generate → render) running end-to-end in one app. It defaults to
`claude-sonnet-5`; change `DEFAULT_MODEL` in `app.py` if you want a
different model.

## What's been verified

- Every sample payload was run through Streamlit's `AppTest` harness with
  every radio button, checkbox, slider, and button exercised (form
  submits, "Next"/"Reveal"/"Verify Answers" clicks included) — zero
  exceptions across all six categories and all four quiz modes.
- The formula evaluator used by the math and engineering interactives
  (`safe_eval_formula`) was tested against a code-injection attempt
  (`__import__("os").system(...)`) and correctly rejects it.

## Two design decisions worth knowing about

1. **The "code editor" for the Coding category doesn't execute code.**
   Running arbitrary student-submitted code is a real security risk
   (sandbox escape, resource exhaustion), so `code_practice` instead shows
   a reference snippet and does keyword-based feedback on the student's
   attempt. If you want real execution later, that needs a proper
   sandboxed runner (e.g. a locked-down container per submission) — not
   something to bolt on with `exec()`.

2. **Formula evaluation (`graph_2d`, `numeric_calculator`) is restricted,
   not fully sandboxed.** `safe_eval_formula` disables builtins and
   whitelists only `math`/`numpy` names plus your declared variables, which
   blocks straightforward injection (see the test above). It is not a
   hardened sandbox — Python's `eval` can't be made fully safe this way.
   Since the formula string is meant to come from your own AI Engine call
   (governed by `ai_system_prompt.md`) rather than an untrusted third
   party, this is a reasonable tradeoff for this use case. For a
   public-facing deployment accepting payloads from strangers, swap in a
   real restricted-evaluation library such as `simpleeval`.

## Extending it

- **New algorithm for the visualizer:** add a `*_steps(...)` generator
  function to `app.py` and register it in the `ALGORITHMS` dict. The AI
  prompt already tells the model which algorithm names exist.
- **New interactive type:** add a `render_*` function, register it in
  `INTERACTIVE_RENDERERS`, and document its fields in `schema.md` +
  `ai_system_prompt.md`.
- **New quiz behavior:** same pattern via `QUIZ_RENDERERS`.

Because the AI/renderer boundary is a JSON schema, every one of these
extensions is a change to pre-tested Python — never to what the AI is
allowed to generate freely.
