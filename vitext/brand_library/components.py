"""
Brand components — higher-level Manim wrappers for common visual patterns.

These compose palette + typography into reusable scene-building blocks:
graphs, highlight boxes, step reveals, transition cards, etc.

The Code Agent is instructed to build scenes from these components rather
than configuring raw Manim Mobjects with ad-hoc parameters.
"""

from manim import (
    VGroup, Scene, Axes, FunctionGraph, Rectangle, RoundedRectangle,
    Circle, Arrow, DashedLine, SurroundingRectangle,
    Write, FadeIn, FadeOut, Create, GrowFromCenter, Transform,
    UP, DOWN, LEFT, RIGHT, ORIGIN, UL, UR, DL, DR,
    config as manim_config,
    LINEAR, DEGREES,
)
import numpy as np

from vitext.brand_library.palette import (
    BRAND_PRIMARY, BRAND_SECONDARY, BRAND_TERTIARY,
    BRAND_BG_DARK, BRAND_BG_MEDIUM, BRAND_BG_LIGHT,
    BRAND_TEXT_LIGHT, BRAND_TEXT_DIM,
    BRAND_FORMULA, BRAND_HIGHLIGHT,
    BRAND_GRAPH_COLORS, BRAND_GRADIENT_PRIMARY,
    OPACITY_MEDIUM, OPACITY_LOW, OPACITY_GHOST,
)
from vitext.brand_library.typography import (
    BrandTitle, BrandSubtitle, BrandBodyText, BrandCaption, BrandFormula,
)


class BrandScene(Scene):
    """
    Base scene class with brand defaults applied.

    Every generated scene should subclass BrandScene instead of raw Scene.
    This ensures:
        - Correct background color
        - Brand-consistent resolution
        - A standard intro/outro pattern

    Usage:
        class MyScene(BrandScene):
            def construct(self):
                title = BrandTitle("My Topic")
                self.play(Write(title))
                self.wait(1)
    """
    def setup(self):
        super().setup()
        self.camera.background_color = BRAND_BG_DARK


class BrandAxes(VGroup):
    """
    Pre-styled 2D axes for plotting functions and data.

    Usage:
        axes = BrandAxes(x_range=[-3, 3], y_range=[-2, 2])
        graph = axes.get_function_graph(lambda x: np.sin(x))
        self.play(Create(axes), Create(graph))
    """
    def __init__(
        self,
        x_range: list = None,
        y_range: list = None,
        x_label: str = "x",
        y_label: str = "y",
        **kwargs
    ):
        x_range = x_range or [-5, 5, 1]
        y_range = y_range or [-3, 3, 1]

        self.axes = Axes(
            x_range=x_range,
            y_range=y_range,
            x_length=10,
            y_length=6,
            axis_config={
                "color": BRAND_TEXT_DIM,
                "stroke_width": 2,
                "include_tip": True,
                "tip_width": 0.2,
                "tip_height": 0.2,
            },
            x_axis_config={"numbers_to_include": list(range(int(x_range[0]), int(x_range[1]) + 1))},
            y_axis_config={"numbers_to_include": list(range(int(y_range[0]), int(y_range[1]) + 1))},
        )

        # Style the axis numbers
        for num in self.axes.x_axis.numbers:
            num.set_color(BRAND_TEXT_DIM).scale(0.7)
        for num in self.axes.y_axis.numbers:
            num.set_color(BRAND_TEXT_DIM).scale(0.7)

        # Axis labels
        x_lab = BrandCaption(x_label).next_to(self.axes.x_axis, RIGHT, buff=0.2)
        y_lab = BrandCaption(y_label).next_to(self.axes.y_axis, UP, buff=0.2)

        super().__init__(self.axes, x_lab, y_lab, **kwargs)

    def get_function_graph(self, func, color_index: int = 0, **kwargs):
        """Plot a function on these axes with a brand color."""
        color = BRAND_GRAPH_COLORS[color_index % len(BRAND_GRAPH_COLORS)]
        return self.axes.plot(func, color=color, stroke_width=3, **kwargs)

    def get_area_under(self, graph, x_range, color_index: int = 0, **kwargs):
        """Shade the area under a graph with brand styling."""
        color = BRAND_GRAPH_COLORS[color_index % len(BRAND_GRAPH_COLORS)]
        return self.axes.get_area(
            graph,
            x_range=x_range,
            color=color,
            opacity=OPACITY_LOW,
            **kwargs,
        )


class BrandHighlightBox(VGroup):
    """
    A rounded rectangle highlight box around a Mobject.

    Usage:
        formula = BrandFormula(r"E = mc^2")
        box = BrandHighlightBox(formula, label="Key Equation")
        self.play(Create(box))
    """
    def __init__(self, mobject, label: str = None, **kwargs):
        box = SurroundingRectangle(
            mobject,
            color=BRAND_PRIMARY,
            buff=0.3,
            corner_radius=0.15,
            stroke_width=2,
        )
        elements = [box]
        if label:
            lbl = BrandCaption(label)
            lbl.next_to(box, UP, buff=0.15)
            lbl.set_color(BRAND_PRIMARY)
            elements.append(lbl)
        super().__init__(*elements, **kwargs)


class BrandCard(VGroup):
    """
    A floating card with title + content for call-out information.

    Usage:
        card = BrandCard(
            title="Remember",
            body="The chain rule applies to composite functions.",
        )
        card.to_edge(RIGHT)
        self.play(FadeIn(card, shift=LEFT * 0.5))
    """
    def __init__(self, title: str, body: str, width: float = 5.0, **kwargs):
        bg = RoundedRectangle(
            width=width,
            height=2.5,
            corner_radius=0.2,
            fill_color=BRAND_BG_MEDIUM,
            fill_opacity=0.9,
            stroke_color=BRAND_PRIMARY,
            stroke_width=1.5,
        )
        title_text = BrandSubtitle(title).scale(0.7)
        title_text.set_color(BRAND_PRIMARY)
        body_text = BrandBodyText(body).scale(0.65)

        content = VGroup(title_text, body_text).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        content.move_to(bg.get_center())

        super().__init__(bg, content, **kwargs)


class BrandTitleCard(VGroup):
    """
    Full-screen title card for scene intros.

    Usage (inside a BrandScene.construct):
        intro = BrandTitleCard("The Chain Rule", "Calculus — Differentiation")
        self.play(FadeIn(intro, shift=UP * 0.3))
        self.wait(2)
        self.play(FadeOut(intro))
    """
    def __init__(self, title: str, subtitle: str = "", **kwargs):
        t = BrandTitle(title)
        elements = [t]
        if subtitle:
            s = BrandSubtitle(subtitle)
            s.next_to(t, DOWN, buff=0.4)
            elements.append(s)

        # Decorative accent line under the title
        line_width = t.width * 0.6
        accent = DashedLine(
            start=LEFT * line_width / 2,
            end=RIGHT * line_width / 2,
            color=BRAND_PRIMARY,
            stroke_width=2,
            dash_length=0.15,
        )
        accent.next_to(elements[-1], DOWN, buff=0.3)
        elements.append(accent)

        super().__init__(*elements, **kwargs)
        self.move_to(ORIGIN)


class BrandStepReveal(VGroup):
    """
    Animated step-by-step reveal — for building up a derivation or process.

    Usage:
        steps = BrandStepReveal([
            "Start with f(g(x))",
            "Differentiate the outer: f'(g(x))",
            "Multiply by inner derivative: f'(g(x)) · g'(x)",
        ])
        for anim in steps.get_reveal_animations():
            self.play(anim)
            self.wait(0.5)
    """
    def __init__(self, step_texts: list[str], **kwargs):
        self.step_mobjects = []
        for i, text in enumerate(step_texts):
            from vitext.brand_library.typography import BrandStepCounter
            step = BrandStepCounter(i + 1, text)
            self.step_mobjects.append(step)

        super().__init__(*self.step_mobjects, **kwargs)
        self.arrange(DOWN, aligned_edge=LEFT, buff=0.5)

    def get_reveal_animations(self):
        """Return a list of FadeIn animations, one per step."""
        return [FadeIn(step, shift=RIGHT * 0.3) for step in self.step_mobjects]


class BrandArrowAnnotation(VGroup):
    """
    An arrow pointing from a label to a target Mobject.

    Usage:
        ann = BrandArrowAnnotation(target_mobject, "This is the key term", direction=UP)
        self.play(FadeIn(ann))
    """
    def __init__(self, target, label_text: str, direction=UP, buff: float = 0.8, **kwargs):
        label = BrandCaption(label_text)
        label.next_to(target, direction, buff=buff)

        arrow = Arrow(
            start=label.get_edge_center(-direction),
            end=target.get_edge_center(direction),
            color=BRAND_SECONDARY,
            stroke_width=2,
            tip_length=0.2,
            buff=0.1,
        )

        super().__init__(label, arrow, **kwargs)
