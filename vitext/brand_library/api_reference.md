# Vitext Brand Library — API Reference

> **This document is the ONLY reference the Code Agent should use.**
> Do NOT import from `manim` directly. Use only the classes below.

## Import

```python
from vitext.brand_library import *
```

This gives you access to everything: colors, typography, and components.

---

## Color Palette (`vitext.brand_library.palette`)

| Constant | Hex | Use |
|---|---|---|
| `BRAND_PRIMARY` | `#6C63FF` | Purple accent, key highlights |
| `BRAND_SECONDARY` | `#FF6584` | Coral pink, secondary accents |
| `BRAND_TERTIARY` | `#43E8D8` | Teal, tertiary / graphs |
| `BRAND_BG_DARK` | `#1A1A2E` | Scene background (auto-set by `BrandScene`) |
| `BRAND_BG_MEDIUM` | `#16213E` | Panel / card background |
| `BRAND_BG_LIGHT` | `#0F3460` | Highlight box background |
| `BRAND_TEXT_LIGHT` | `#E8E8F0` | Primary text |
| `BRAND_TEXT_DIM` | `#A0A0B8` | Captions, secondary text |
| `BRAND_FORMULA` | `#61DAFB` | LaTeX formulas |
| `BRAND_HIGHLIGHT` | `#FFD93D` | Yellow emphasis |
| `BRAND_SUCCESS` | `#00D9A3` | Correct / positive |
| `BRAND_WARNING` | `#FFB347` | Caution |
| `BRAND_ERROR` | `#FF4757` | Error / danger |

Multi-series: `BRAND_GRAPH_COLORS[0..6]` — use index to distinguish lines.

Opacity: `OPACITY_FULL`, `OPACITY_HIGH`, `OPACITY_MEDIUM`, `OPACITY_LOW`, `OPACITY_GHOST`.

---

## Typography (`vitext.brand_library.typography`)

### `BrandTitle(text)`
Large heading, 56pt, bold, light color.
```python
title = BrandTitle("The Chain Rule")
self.play(Write(title))
```

### `BrandSubtitle(text)`
Medium heading, 36pt, dim color.
```python
sub = BrandSubtitle("Calculus — Differentiation")
sub.next_to(title, DOWN, buff=0.3)
```

### `BrandBodyText(text)`
Body text, 28pt. For explanations and annotations.
```python
note = BrandBodyText("We apply the outer derivative first...")
note.to_edge(DOWN, buff=0.5)
```

### `BrandCaption(text)`
Small text, 20pt, dim. Footnotes, step labels.
```python
cap = BrandCaption("Step 1 of 4")
cap.to_corner(DR)
```

### `BrandFormula(*tex_strings)`
LaTeX math, cyan color, 48pt.
```python
eq = BrandFormula(r"\frac{dy}{dx} = \frac{dy}{du} \cdot \frac{du}{dx}")
```

### `BrandFormulaHighlighted(*tex_strings)`
Key equations, yellow, 52pt.
```python
key = BrandFormulaHighlighted(r"E = mc^2")
```

### `BrandCodeBlock(text)`
Monospace code, 24pt. For showing code snippets.
```python
code = BrandCodeBlock("def f(x):\n    return x ** 2")
```

### `BrandBulletList(*items, bullet="•")`
Bullet list, auto-arranged vertically.
```python
points = BrandBulletList("Point one", "Point two", "Point three")
self.play(FadeIn(points, shift=UP * 0.3, lag_ratio=0.2))
```

### `BrandStepCounter(step_number, description)`
"Step N" label + description on same line.
```python
step = BrandStepCounter(1, "Differentiate the outer function")
```

---

## Components (`vitext.brand_library.components`)

### `BrandScene` (base class)
**Always subclass this instead of `Scene`.**
Sets dark background automatically.
```python
class MyScene(BrandScene):
    def construct(self):
        ...
```

### `BrandAxes(x_range, y_range, x_label, y_label)`
Pre-styled 2D axes.
```python
axes = BrandAxes(x_range=[-3, 3, 1], y_range=[-2, 2, 1])
graph = axes.get_function_graph(lambda x: np.sin(x), color_index=0)
area = axes.get_area_under(graph, x_range=[0, 2])
self.play(Create(axes), Create(graph))
```

### `BrandHighlightBox(mobject, label=None)`
Rounded rectangle around any Mobject.
```python
box = BrandHighlightBox(formula, label="Key Equation")
```

### `BrandCard(title, body, width=5.0)`
Floating info card with title + body text.
```python
card = BrandCard("Remember", "Chain rule applies to composites.")
card.to_edge(RIGHT)
self.play(FadeIn(card, shift=LEFT * 0.5))
```

### `BrandTitleCard(title, subtitle="")`
Full-screen intro card with decorative accent line.
```python
intro = BrandTitleCard("The Chain Rule", "Calculus — Differentiation")
self.play(FadeIn(intro, shift=UP * 0.3))
self.wait(2)
self.play(FadeOut(intro))
```

### `BrandStepReveal(step_texts: list[str])`
Animated step-by-step reveal.
```python
steps = BrandStepReveal([
    "Start with f(g(x))",
    "Differentiate the outer",
    "Multiply by inner derivative",
])
for anim in steps.get_reveal_animations():
    self.play(anim)
    self.wait(0.5)
```

### `BrandArrowAnnotation(target, label_text, direction=UP, buff=0.8)`
Arrow + label pointing at a Mobject.
```python
ann = BrandArrowAnnotation(formula[3], "the inner function", direction=DOWN)
self.play(FadeIn(ann))
```

---

## Rules for the Code Agent

1. **Import only `from vitext.brand_library import *`** — never `from manim import ...`
2. **Subclass `BrandScene`** — never raw `Scene`
3. **Use named colors** — never raw hex codes
4. **Use typography classes** — never raw `Text()` or `MathTex()`
5. **Each scene class must be self-contained** — no global state between scenes
6. **Keep animations under 30 seconds per scene** — shorter chunks = better reliability
