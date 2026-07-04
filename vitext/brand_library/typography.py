"""
Brand typography — wrapper classes for all text rendering in Vitext.

Instead of calling manim.Text() or manim.MathTex() with manual styling,
the Code Agent uses these classes which enforce brand fonts, sizes, colors,
and positioning automatically.
"""

from manim import Text, MathTex, Tex, VGroup, DOWN, UP, LEFT, RIGHT, ORIGIN

from vitext.brand_library.palette import (
    BRAND_TEXT_LIGHT,
    BRAND_TEXT_DIM,
    BRAND_PRIMARY,
    BRAND_FORMULA,
    BRAND_HIGHLIGHT,
)


# ── Font stack ────────────────────────────────────────────────────────
# These are the ONLY fonts the Code Agent should use.
FONT_HEADING = "Inter"
FONT_BODY    = "Inter"
FONT_MONO    = "JetBrains Mono"


class BrandTitle(Text):
    """
    Large title text — used for scene titles and section headings.

    Usage:
        title = BrandTitle("The Chain Rule")
        self.play(Write(title))
    """
    def __init__(self, text: str, **kwargs):
        defaults = dict(
            font=FONT_HEADING,
            font_size=56,
            color=BRAND_TEXT_LIGHT,
            weight="BOLD",
        )
        defaults.update(kwargs)
        super().__init__(text, **defaults)


class BrandSubtitle(Text):
    """
    Medium subtitle — used below titles or for section sub-headings.

    Usage:
        subtitle = BrandSubtitle("A fundamental rule of calculus")
        subtitle.next_to(title, DOWN, buff=0.3)
    """
    def __init__(self, text: str, **kwargs):
        defaults = dict(
            font=FONT_HEADING,
            font_size=36,
            color=BRAND_TEXT_DIM,
        )
        defaults.update(kwargs)
        super().__init__(text, **defaults)


class BrandBodyText(Text):
    """
    Body text — for explanations, narration cues, annotations.

    Usage:
        explanation = BrandBodyText("We differentiate the outer function first...")
        explanation.to_edge(DOWN, buff=0.5)
    """
    def __init__(self, text: str, **kwargs):
        defaults = dict(
            font=FONT_BODY,
            font_size=28,
            color=BRAND_TEXT_LIGHT,
        )
        defaults.update(kwargs)
        super().__init__(text, **defaults)


class BrandCaption(Text):
    """
    Small caption text — for footnotes, source attributions, step labels.

    Usage:
        step_label = BrandCaption("Step 1 of 4")
        step_label.to_corner(DR)
    """
    def __init__(self, text: str, **kwargs):
        defaults = dict(
            font=FONT_BODY,
            font_size=20,
            color=BRAND_TEXT_DIM,
        )
        defaults.update(kwargs)
        super().__init__(text, **defaults)


class BrandFormula(MathTex):
    """
    LaTeX math formula with brand styling.

    Usage:
        formula = BrandFormula(r"\\frac{dy}{dx} = \\frac{dy}{du} \\cdot \\frac{du}{dx}")
        self.play(Write(formula))
    """
    def __init__(self, *tex_strings: str, **kwargs):
        defaults = dict(
            color=BRAND_FORMULA,
            font_size=48,
        )
        defaults.update(kwargs)
        super().__init__(*tex_strings, **defaults)


class BrandFormulaHighlighted(MathTex):
    """
    Highlighted math formula — for emphasizing a key equation.

    Usage:
        key_eq = BrandFormulaHighlighted(r"E = mc^2")
    """
    def __init__(self, *tex_strings: str, **kwargs):
        defaults = dict(
            color=BRAND_HIGHLIGHT,
            font_size=52,
        )
        defaults.update(kwargs)
        super().__init__(*tex_strings, **defaults)


class BrandCodeBlock(Text):
    """
    Monospace code text for showing code snippets in the video.

    Usage:
        code = BrandCodeBlock("def chain_rule(f, g):\\n    return f_prime(g(x)) * g_prime(x)")
    """
    def __init__(self, text: str, **kwargs):
        defaults = dict(
            font=FONT_MONO,
            font_size=24,
            color=BRAND_TEXT_LIGHT,
            line_spacing=1.4,
        )
        defaults.update(kwargs)
        super().__init__(text, **defaults)


class BrandBulletList(VGroup):
    """
    Bullet-point list with consistent spacing and styling.

    Usage:
        points = BrandBulletList(
            "Differentiate the outer function",
            "Multiply by the derivative of the inner function",
            "Simplify the result",
        )
        self.play(FadeIn(points, shift=UP * 0.3, lag_ratio=0.2))
    """
    def __init__(self, *items: str, bullet: str = "•", **kwargs):
        bullet_size = kwargs.pop("font_size", 26)
        texts = []
        for item in items:
            line = Text(
                f"{bullet}  {item}",
                font=FONT_BODY,
                font_size=bullet_size,
                color=BRAND_TEXT_LIGHT,
            )
            texts.append(line)
        super().__init__(*texts, **kwargs)
        self.arrange(DOWN, aligned_edge=LEFT, buff=0.35)


class BrandStepCounter(VGroup):
    """
    "Step N" label + description, for step-by-step walkthroughs.

    Usage:
        step = BrandStepCounter(1, "Apply the outer derivative")
        self.play(FadeIn(step))
    """
    def __init__(self, step_number: int, description: str, **kwargs):
        label = Text(
            f"Step {step_number}",
            font=FONT_HEADING,
            font_size=30,
            color=BRAND_PRIMARY,
            weight="BOLD",
        )
        desc = Text(
            description,
            font=FONT_BODY,
            font_size=26,
            color=BRAND_TEXT_LIGHT,
        )
        desc.next_to(label, RIGHT, buff=0.4)
        super().__init__(label, desc, **kwargs)
