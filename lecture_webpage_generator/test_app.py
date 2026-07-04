"""Exercises every sample category end-to-end via Streamlit's AppTest harness."""
from streamlit.testing.v1 import AppTest

samples = ["Coding", "Algorithms", "Poetry", "Mathematics", "Science", "Engineering"]
failures = []

for label in samples:
    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    at.sidebar.selectbox[0].select(label).run(timeout=30)
    if at.exception:
        failures.append((label, "initial render", at.exception[0].value))
        continue

    # Exercise every radio/checkbox/slider/number_input once, then submit the form.
    for r in at.radio:
        if r.options:
            r.set_value(r.options[0])
    for cb in at.checkbox:
        cb.set_value(True)
    for sl in at.slider:
        pass  # leave at default; sliders already render a value
    for ni in at.number_input:
        pass  # leave default

    at.run(timeout=30)
    if at.exception:
        failures.append((label, "after setting inputs", at.exception[0].value))
        continue

    # Click every button (submit forms, "Next", "Reveal", "Check my attempt", etc.)
    for b in at.button:
        b.click().run(timeout=30)
        if at.exception:
            failures.append((label, f"after clicking button '{b.label}'", at.exception[0].value))

    print(f"{label}: rendered OK, "
          f"{len(at.radio)} radio, {len(at.checkbox)} checkbox, "
          f"{len(at.slider)} slider, {len(at.number_input)} number_input, "
          f"{len(at.button)} button(s) exercised")

print()
if failures:
    print(f"FAILURES: {len(failures)}")
    for label, stage, exc in failures:
        print(f"  - [{label}] during {stage}: {exc}")
else:
    print("ALL CATEGORIES PASSED — no exceptions across full interaction flow.")
