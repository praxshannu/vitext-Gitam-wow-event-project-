"""
Automated Interactive Streamlit Webpage Generator
==================================================

Hybrid Template Engine implementation.

Design principle (carried over from the architecture blueprint, extended to
all six subject categories): the AI never writes Streamlit / Python code.
It only ever produces a JSON payload that matches the schema documented in
schema.md. This file is the ONE pre-built rendering engine that turns any
valid payload into a fully interactive page. Because the AI's output surface
is "strings, numbers, and arrays" rather than "code", it can't break syntax,
which is what makes zero-shot reliability achievable.

Run with:  streamlit run app.py
"""

import glob
import json
import math
import os
from collections import deque



import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_payloads")
DEFAULT_MODEL = "claude-sonnet-5"


# ---------------------------------------------------------------------------
# Safe formula evaluation (math / engineering interactives)
# ---------------------------------------------------------------------------
# Raw eval() on an AI-produced string (as in the original math-only proof of
# concept) is not actually "secure" just because a comment says so. This
# restricts eval to a whitelist of math/numpy names and the slider/input
# variables, with builtins disabled. It is NOT a full sandbox (attribute
# access on the whitelisted objects still exists), so this app should only
# be pointed at trusted transcript sources / your own AI Engine calls, not
# at arbitrary third-party payloads. For a public-facing deployment, swap
# this for a real restricted-evaluation library (e.g. `simpleeval`).
_SAFE_MATH_NAMES = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
_SAFE_NUMPY_NAMES = {"np": np, "pi": np.pi, "e": np.e}


def safe_eval_formula(expr, variables):
    allowed = {"__builtins__": {}}
    allowed.update(_SAFE_MATH_NAMES)
    allowed.update(_SAFE_NUMPY_NAMES)
    allowed.update(variables)
    try:
        return eval(expr, allowed, {})  # noqa: S307 - restricted namespace above
    except Exception as e:
        raise ValueError(f"Could not evaluate formula '{expr}': {e}")


# ---------------------------------------------------------------------------
# Algorithm step-generators (pre-built, not AI-generated)
# ---------------------------------------------------------------------------
# The AI only tells us WHICH algorithm and WHAT starting data to use. These
# pre-coded generators do the actual execution, so there's no risk of the
# model producing incorrect or unsafe algorithm code.

def bubble_sort_steps(arr):
    arr = list(arr)
    n = len(arr)
    steps = [{"array": arr.copy(), "highlight": [], "message": "Initial array"}]
    for i in range(n):
        for j in range(0, n - i - 1):
            steps.append({"array": arr.copy(), "highlight": [j, j + 1],
                          "message": f"Compare positions {j} and {j + 1}"})
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                steps.append({"array": arr.copy(), "highlight": [j, j + 1],
                              "message": f"Swap → {arr[j]}, {arr[j + 1]}"})
    steps.append({"array": arr.copy(), "highlight": [], "message": "Sorted!"})
    return steps


def binary_search_steps(arr, target):
    arr = sorted(arr)
    steps = []
    lo, hi = 0, len(arr) - 1
    steps.append({"array": arr.copy(), "highlight": [], "message": f"Searching for {target} in a sorted array"})
    found = False
    while lo <= hi:
        mid = (lo + hi) // 2
        steps.append({"array": arr.copy(), "highlight": list(range(lo, hi + 1)) + [mid],
                      "message": f"Check middle index {mid} (value {arr[mid]})"})
        if arr[mid] == target:
            steps.append({"array": arr.copy(), "highlight": [mid], "message": f"Found {target} at index {mid}!"})
            found = True
            break
        elif arr[mid] < target:
            lo = mid + 1
            steps.append({"array": arr.copy(), "highlight": list(range(lo, hi + 1)) if lo <= hi else [],
                          "message": f"{arr[mid]} < {target}: search the right half"})
        else:
            hi = mid - 1
            steps.append({"array": arr.copy(), "highlight": list(range(lo, hi + 1)) if lo <= hi else [],
                          "message": f"{arr[mid]} > {target}: search the left half"})
    if not found:
        steps.append({"array": arr.copy(), "highlight": [], "message": f"{target} was not found"})
    return steps


def bfs_steps(graph, start):
    visited = {start}
    queue = deque([start])
    order = []
    steps = [{"visited": list(visited), "queue": list(queue), "message": f"Start BFS at {start}"}]
    while queue:
        node = queue.popleft()
        order.append(node)
        steps.append({"visited": list(visited), "queue": list(queue), "message": f"Visit {node}"})
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
                steps.append({"visited": list(visited), "queue": list(queue),
                              "message": f"Discover {neighbor} from {node}"})
    steps.append({"visited": list(visited), "queue": [], "message": f"BFS complete. Order: {', '.join(order)}"})
    return steps


def dijkstra_steps(graph, start):
    import heapq
    dist = {node: float("inf") for node in graph}
    dist[start] = 0
    visited = set()
    pq = [(0, start)]
    steps = [{"distances": dict(dist), "visited": list(visited), "message": f"Start Dijkstra at {start}"}]
    while pq:
        d, node = heapq.heappop(pq)
        if node in visited:
            continue
        visited.add(node)
        steps.append({"distances": dict(dist), "visited": list(visited), "message": f"Finalize distance to {node}: {d}"})
        for neighbor, weight in graph.get(node, {}).items():
            if neighbor in visited:
                continue
            nd = d + weight
            if nd < dist[neighbor]:
                dist[neighbor] = nd
                heapq.heappush(pq, (nd, neighbor))
                steps.append({"distances": dict(dist), "visited": list(visited),
                              "message": f"Update distance to {neighbor}: {nd}"})
    steps.append({"distances": dict(dist), "visited": list(visited), "message": "Dijkstra complete"})
    return steps


ALGORITHMS = {
    "bubble_sort": bubble_sort_steps,
    "binary_search": binary_search_steps,
    "bfs": bfs_steps,
    "dijkstra": dijkstra_steps,
}


# ---------------------------------------------------------------------------
# Content block rendering (shared across all categories)
# ---------------------------------------------------------------------------

def render_content_blocks(blocks):
    for block in blocks:
        btype = block.get("type")
        if btype == "text":
            st.write(block["value"])
        elif btype == "latex_formula":
            st.latex(block["value"])
        elif btype == "image":
            st.image(block["url"], caption=block.get("caption", ""), width="stretch")
        elif btype == "text_with_links":
            parts = []
            for seg in block.get("segments", []):
                if seg.get("url"):
                    parts.append(f"[{seg['text']}]({seg['url']})")
                else:
                    parts.append(seg["text"])
            st.markdown("".join(parts))
        else:
            st.warning(f"Unknown content block type: {btype}")


# ---------------------------------------------------------------------------
# Interactive renderers, one per interactive_config.type
# ---------------------------------------------------------------------------

def render_graph_2d(cfg):
    st.subheader(cfg.get("title", "Interactive Graph Simulator"))
    controls = cfg.get("controls", [])
    values = {}
    cols = st.columns(len(controls)) if controls else [st]
    for idx, ctrl in enumerate(controls):
        with cols[idx]:
            values[ctrl["key"]] = st.slider(ctrl["label"], float(ctrl["min"]), float(ctrl["max"]), float(ctrl["default"]))
    x_range = cfg.get("x_range", [0, 10])
    x = np.linspace(x_range[0], x_range[1], 500)
    try:
        y = safe_eval_formula(cfg["equation"], {**values, "x": x})
    except ValueError as e:
        st.error(str(e))
        return
    fig = px.line(x=x, y=y, labels={"x": "x", "y": "y"})
    st.plotly_chart(fig, width="stretch")


def render_shape_2d(cfg):
    st.subheader(cfg.get("title", "Interactive Shape"))
    shape = cfg.get("shape", "circle")
    controls = cfg.get("controls", [])
    values = {}
    cols = st.columns(len(controls)) if controls else [st]
    for idx, ctrl in enumerate(controls):
        with cols[idx]:
            values[ctrl["key"]] = st.slider(ctrl["label"], float(ctrl["min"]), float(ctrl["max"]), float(ctrl["default"]))

    fig = go.Figure()
    if shape == "circle":
        r = values.get("radius", 1)
        theta = np.linspace(0, 2 * np.pi, 200)
        fig.add_trace(go.Scatter(x=r * np.cos(theta), y=r * np.sin(theta), mode="lines", fill="toself"))
        st.caption(f"Area ≈ {math.pi * r ** 2:.2f} · Circumference ≈ {2 * math.pi * r:.2f}")
    elif shape == "rectangle":
        w, h = values.get("width", 1), values.get("height", 1)
        fig.add_trace(go.Scatter(x=[0, w, w, 0, 0], y=[0, 0, h, h, 0], mode="lines", fill="toself"))
        st.caption(f"Area = {w * h:.2f} · Perimeter = {2 * (w + h):.2f}")
    elif shape == "triangle":
        a, b, c = values.get("side_a", 1), values.get("side_b", 1), values.get("side_c", 1)
        try:
            angle_c = math.acos((a ** 2 + b ** 2 - c ** 2) / (2 * a * b))
            x3, y3 = b * math.cos(angle_c), b * math.sin(angle_c)
            fig.add_trace(go.Scatter(x=[0, a, x3, 0], y=[0, 0, y3, 0], mode="lines", fill="toself"))
            s = (a + b + c) / 2
            area = math.sqrt(max(s * (s - a) * (s - b) * (s - c), 0))
            st.caption(f"Perimeter = {a + b + c:.2f} · Area ≈ {area:.2f}")
        except ValueError:
            st.error("Those three side lengths can't form a valid triangle.")
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, width="stretch")


def render_code_practice(cfg):
    st.subheader(cfg.get("title", "Practice Area"))
    language = cfg.get("language", "python")
    if cfg.get("reference_code"):
        st.caption("Reference example")
        st.code(cfg["reference_code"], language=language)
    st.write(cfg.get("prompt", "Try writing your own version below:"))
    user_code = st.text_area("Your code", height=180, key="code_practice_input")
    if st.button("Check my attempt"):
        keywords = cfg.get("expected_keywords", [])
        if not keywords:
            st.info("Compare your attempt with the reference above.")
        else:
            missing = [kw for kw in keywords if kw.lower() not in user_code.lower()]
            if not missing:
                st.success("Looks complete — your code touches all the key elements. 🎉")
            else:
                st.warning("You're close. Consider whether your code includes: " + ", ".join(missing))
    st.caption("This is a review sandbox — code isn't executed here, so compare your attempt against the "
               "reference and explanation instead of expecting it to run.")


def render_algorithm_visualizer(cfg):
    st.subheader(cfg.get("title", "Step-by-Step Algorithm Visualizer"))
    algo_name = cfg.get("algorithm")
    input_type = cfg.get("input_type", "array")
    default_input = cfg.get("default_input")
    gen = ALGORITHMS.get(algo_name)
    if gen is None:
        st.warning(f"Algorithm '{algo_name}' isn't in the built-in visualizer library yet.")
        return

    steps = None
    if input_type == "array":
        raw = st.text_input("Custom array (comma-separated numbers)",
                             value=",".join(str(x) for x in default_input))
        try:
            arr = [int(x) if float(x).is_integer() else float(x) for x in raw.split(",") if x.strip() != ""]
        except ValueError:
            st.error("Please enter valid comma-separated numbers.")
            return
        if algo_name == "binary_search":
            target = st.number_input("Search target", value=default_input[0] if default_input else 0)
            steps = gen(arr, target)
        else:
            steps = gen(arr)
    elif input_type == "graph":
        st.caption('Edit the graph as JSON, e.g. {"A": ["B", "C"]} or, for Dijkstra, {"A": {"B": 4}}')
        raw = st.text_area("Graph structure (JSON)", value=json.dumps(default_input, indent=2))
        try:
            graph = json.loads(raw)
        except json.JSONDecodeError:
            st.error("Graph must be valid JSON.")
            return
        if not graph:
            st.error("Graph can't be empty.")
            return
        start_node = st.selectbox("Start node", options=list(graph.keys()))
        steps = gen(graph, start_node)
    else:
        st.warning("Unsupported input_type for algorithm visualizer.")
        return

    key = f"algo_step_{algo_name}"
    if key not in st.session_state:
        st.session_state[key] = 0
    st.session_state[key] = st.slider("Step", 0, len(steps) - 1, min(st.session_state[key], len(steps) - 1))
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("⏮ Previous") and st.session_state[key] > 0:
            st.session_state[key] -= 1
    with c2:
        if st.button("Reset"):
            st.session_state[key] = 0
    with c3:
        if st.button("Next ⏭") and st.session_state[key] < len(steps) - 1:
            st.session_state[key] += 1

    step = steps[st.session_state[key]]
    st.info(step.get("message", ""))
    if "array" in step:
        colors = ["#636EFA"] * len(step["array"])
        for idx in step.get("highlight", []):
            if isinstance(idx, int) and 0 <= idx < len(colors):
                colors[idx] = "#EF553B"
        fig = go.Figure(go.Bar(x=list(range(len(step["array"]))), y=step["array"], marker_color=colors))
        st.plotly_chart(fig, width="stretch")
    elif "distances" in step:
        st.table({"Node": list(step["distances"].keys()),
                  "Distance": ["∞" if v == float("inf") else v for v in step["distances"].values()]})
        st.write("Visited:", ", ".join(step["visited"]) or "—")
    elif "visited" in step:
        st.write("Visited:", ", ".join(step["visited"]) or "—")
        st.write("Queue:", ", ".join(step["queue"]) or "—")


def render_media_gallery(cfg):
    st.subheader(cfg.get("title", "Visual Explainer"))
    images = cfg.get("images", [])
    if images:
        cols = st.columns(min(len(images), 3))
        for idx, img in enumerate(images):
            with cols[idx % len(cols)]:
                st.image(img["url"], caption=img.get("caption", ""), width="stretch")
    if cfg.get("simulation_note"):
        st.info(cfg["simulation_note"])


def render_numeric_calculator(cfg):
    st.subheader(cfg.get("title", "Interactive Calculator"))
    inputs = cfg.get("inputs", [])
    values = {}
    cols = st.columns(len(inputs)) if inputs else [st]
    for idx, inp in enumerate(inputs):
        with cols[idx]:
            values[inp["key"]] = st.number_input(
                f"{inp['label']} ({inp.get('unit', '')})".strip(),
                min_value=float(inp.get("min", -1e9)),
                max_value=float(inp.get("max", 1e9)),
                value=float(inp.get("default", 0)),
            )
    try:
        result = safe_eval_formula(cfg["formula"], values)
        st.metric(cfg.get("output_label", "Result"), f"{result:.4f} {cfg.get('output_unit', '')}".strip())
    except ValueError as e:
        st.error(str(e))


INTERACTIVE_RENDERERS = {
    "graph_2d": render_graph_2d,
    "shape_2d": render_shape_2d,
    "code_practice": render_code_practice,
    "algorithm_visualizer": render_algorithm_visualizer,
    "media_gallery": render_media_gallery,
    "numeric_calculator": render_numeric_calculator,
}


# ---------------------------------------------------------------------------
# Quiz renderers, one per quiz_form.mode
# ---------------------------------------------------------------------------

def _collect_answers(questions, key_prefix):
    answers = {}
    for i, q in enumerate(questions):
        if q.get("type") == "multi":
            st.write(f"**{i + 1}. {q['question']}**")
            selected = [j for j, opt in enumerate(q["options"])
                        if st.checkbox(opt, key=f"{key_prefix}_{i}_{j}")]
            answers[i] = selected
        else:
            choice = st.radio(f"**{i + 1}. {q['question']}**", q["options"], key=f"{key_prefix}_{i}")
            answers[i] = q["options"].index(choice)
    return answers


def render_quiz_immediate(quiz):
    # Used for both "instant_verify" (coding/algorithms) and "tickbox"
    # (poetry/science) — both give per-question feedback the moment the
    # form is submitted.
    st.subheader(quiz.get("title", "Quick Check"))
    questions = quiz.get("questions", [])
    with st.form("quiz_immediate_form"):
        answers = _collect_answers(questions, "imm")
        submitted = st.form_submit_button("Verify Answers")
    if submitted:
        score = 0
        for i, q in enumerate(questions):
            correct = set(q["correct_indices"])
            given = set(answers[i]) if isinstance(answers[i], list) else {answers[i]}
            if given == correct:
                st.success(f"Question {i + 1}: Correct! 🎉")
                score += 1
            else:
                st.error(f"Question {i + 1}: Not quite.")
                if q.get("explanation"):
                    st.caption(f"💡 {q['explanation']}")
        st.info(f"Score: {score}/{len(questions)}")


def render_quiz_delayed(quiz):
    st.subheader(quiz.get("title", "Challenge Quiz"))
    questions = quiz.get("questions", [])
    with st.form("quiz_delayed_form"):
        answers = _collect_answers(questions, "delayed")
        submitted = st.form_submit_button("Submit Final Answers")
    if submitted:
        st.session_state["delayed_answers"] = answers
        st.session_state["delayed_submitted"] = True
        st.success("Answers submitted. Reveal the answer key below whenever you're ready.")
    if st.session_state.get("delayed_submitted"):
        if st.button("Reveal Answer Key"):
            saved = st.session_state.get("delayed_answers", {})
            score = 0
            for i, q in enumerate(questions):
                correct = set(q["correct_indices"])
                given = set(saved.get(i, [])) if isinstance(saved.get(i), list) else {saved.get(i)}
                ok = given == correct
                score += int(ok)
                correct_labels = ", ".join(q["options"][k] for k in q["correct_indices"])
                st.markdown(f"{'✅' if ok else '❌'} **Q{i + 1}:** {q['question']}  \nCorrect answer: {correct_labels}")
                if q.get("explanation"):
                    st.caption(q["explanation"])
            st.info(f"Final score: {score}/{len(questions)}")


def render_quiz_comprehensive(quiz):
    st.subheader(quiz.get("title", "Comprehensive Technical Assessment"))
    questions = quiz.get("questions", [])
    pass_threshold = quiz.get("pass_threshold", 0.7)
    with st.form("quiz_comprehensive_form"):
        answers = _collect_answers(questions, "comp")
        submitted = st.form_submit_button("Submit for Validation")
    if submitted:
        results = []
        for i, q in enumerate(questions):
            correct = set(q["correct_indices"])
            given = set(answers[i]) if isinstance(answers[i], list) else {answers[i]}
            results.append(given == correct)
        score = sum(results)
        pct = score / len(questions) if questions else 0
        st.write("### Validation Report")
        for i, (q, ok) in enumerate(zip(questions, results)):
            st.write(f"{'✅' if ok else '❌'} Q{i + 1}: {q['question']}")
            if not ok and q.get("explanation"):
                st.caption(q["explanation"])
        if pct >= pass_threshold:
            st.success(f"Validation PASSED — {score}/{len(questions)} correct ({pct:.0%}).")
        else:
            st.error(f"Validation FAILED — {score}/{len(questions)} correct ({pct:.0%}). Review the explanations above.")


QUIZ_RENDERERS = {
    "instant_verify": render_quiz_immediate,
    "tickbox": render_quiz_immediate,
    "delayed_key": render_quiz_delayed,
    "comprehensive": render_quiz_comprehensive,
}


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------

def validate_payload(data):
    errors = []
    if not isinstance(data, dict):
        return ["Payload must be a JSON object."]
    for key in ("subject_category", "page_title", "content_blocks", "quiz_form"):
        if key not in data:
            errors.append(f"Missing required field: '{key}'")
    if "quiz_form" in data:
        qf = data["quiz_form"]
        if not isinstance(qf, dict) or "mode" not in qf or "questions" not in qf:
            errors.append("quiz_form must be an object with 'mode' and 'questions'")
        elif qf["mode"] not in QUIZ_RENDERERS:
            errors.append(f"Unknown quiz mode: '{qf['mode']}'. Expected one of {list(QUIZ_RENDERERS)}")
    cfg = data.get("interactive_config")
    if cfg:
        if "type" not in cfg:
            errors.append("interactive_config must include 'type'")
        elif cfg["type"] not in INTERACTIVE_RENDERERS:
            errors.append(f"Unknown interactive type: '{cfg['type']}'. Expected one of {list(INTERACTIVE_RENDERERS)}")
    return errors


# ---------------------------------------------------------------------------
# Optional: live transcript -> JSON generation via the Anthropic API
# ---------------------------------------------------------------------------

def generate_from_transcript(transcript_text, api_key, model=DEFAULT_MODEL):
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    prompt_path = os.path.join(os.path.dirname(__file__), "ai_system_prompt.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript_text}"}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Lecture → Interactive Webpage", layout="wide")
    st.sidebar.title("📚 Lecture Webpage Generator")
    source = st.sidebar.radio(
        "Data source",
        ["Sample gallery", "Upload JSON payload", "Generate from transcript"],
    )

    data = None

    if source == "Sample gallery":
        sample_files = sorted(glob.glob(os.path.join(SAMPLE_DIR, "*.json")))
        if not sample_files:
            st.sidebar.warning("No sample payloads found in sample_payloads/.")
        else:
            labels = [os.path.splitext(os.path.basename(f))[0].replace("_", " ").title() for f in sample_files]
            choice = st.sidebar.selectbox("Choose a sample", labels)
            with open(sample_files[labels.index(choice)], "r", encoding="utf-8") as f:
                data = json.load(f)

    elif source == "Upload JSON payload":
        uploaded = st.sidebar.file_uploader("Upload a JSON file matching schema.md", type=["json"])
        if uploaded:
            try:
                data = json.load(uploaded)
            except json.JSONDecodeError as e:
                st.sidebar.error(f"Invalid JSON: {e}")

    else:
        api_key = st.sidebar.text_input("Anthropic API key", type="password",
                                         value=os.environ.get("ANTHROPIC_API_KEY", ""))
        transcript = st.sidebar.text_area("Paste lecture transcript", height=200)
        if st.sidebar.button("Generate webpage"):
            if not api_key:
                st.sidebar.error("An API key is required for live generation.")
            elif not transcript.strip():
                st.sidebar.error("Paste a transcript first.")
            else:
                with st.spinner("Analyzing transcript and building your page..."):
                    try:
                        st.session_state["generated_data"] = generate_from_transcript(transcript, api_key)
                    except Exception as e:
                        st.sidebar.error(f"Generation failed: {e}")
        data = st.session_state.get("generated_data")

    if not data:
        st.title("Lecture → Interactive Webpage Generator")
        st.write("Pick a data source in the sidebar — a sample, a JSON payload, or a transcript to analyze.")
        return

    errors = validate_payload(data)
    if errors:
        st.error("This payload doesn't match the expected schema:")
        for e in errors:
            st.write(f"- {e}")
        return

    st.title(data["page_title"])
    st.caption(f"Category: {data['subject_category'].replace('_', ' ').title()}")
    render_content_blocks(data.get("content_blocks", []))

    cfg = data.get("interactive_config")
    if cfg:
        st.markdown("---")
        INTERACTIVE_RENDERERS[cfg["type"]](cfg)

    quiz = data.get("quiz_form")
    if quiz:
        st.markdown("---")
        QUIZ_RENDERERS[quiz["mode"]](quiz)


if __name__ == "__main__":
    main()
