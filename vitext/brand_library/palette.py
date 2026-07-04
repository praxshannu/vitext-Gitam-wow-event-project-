"""
Brand color palette — the single source of truth for all colors in Vitext.

The Code Agent is instructed to use ONLY these named constants.
Raw hex codes in generated Manim code are a style-drift violation.
"""

from manim import ManimColor

# ── Primary brand colors ──────────────────────────────────────────────
BRAND_PRIMARY       = ManimColor("#6C63FF")   # Vibrant purple — accents, key highlights
BRAND_SECONDARY     = ManimColor("#FF6584")   # Coral pink — secondary accents
BRAND_TERTIARY      = ManimColor("#43E8D8")   # Teal — tertiary, graphs

# ── Background ────────────────────────────────────────────────────────
BRAND_BG_DARK       = ManimColor("#1A1A2E")   # Deep navy — default scene background
BRAND_BG_MEDIUM     = ManimColor("#16213E")   # Slightly lighter panel background
BRAND_BG_LIGHT      = ManimColor("#0F3460")   # Card / highlight box background

# ── Text ──────────────────────────────────────────────────────────────
BRAND_TEXT_LIGHT     = ManimColor("#E8E8F0")   # Primary text on dark backgrounds
BRAND_TEXT_DIM       = ManimColor("#A0A0B8")   # Secondary / caption text
BRAND_TEXT_DARK      = ManimColor("#1A1A2E")   # Text on light backgrounds (rare)

# ── Semantic colors ───────────────────────────────────────────────────
BRAND_SUCCESS        = ManimColor("#00D9A3")   # Correct / positive
BRAND_WARNING        = ManimColor("#FFB347")   # Caution / attention
BRAND_ERROR          = ManimColor("#FF4757")   # Wrong / danger
BRAND_FORMULA        = ManimColor("#61DAFB")   # LaTeX / math formulas
BRAND_HIGHLIGHT      = ManimColor("#FFD93D")   # Yellow highlight for emphasis

# ── Graph / Plot colors (ordered for multi-series charts) ─────────────
BRAND_GRAPH_COLORS = [
    ManimColor("#6C63FF"),   # Purple
    ManimColor("#FF6584"),   # Coral
    ManimColor("#43E8D8"),   # Teal
    ManimColor("#FFB347"),   # Orange
    ManimColor("#00D9A3"),   # Green
    ManimColor("#61DAFB"),   # Cyan
    ManimColor("#FFD93D"),   # Yellow
]

# ── Gradient pairs (start, end) for animated fills ────────────────────
BRAND_GRADIENT_PRIMARY   = (ManimColor("#6C63FF"), ManimColor("#43E8D8"))
BRAND_GRADIENT_WARM      = (ManimColor("#FF6584"), ManimColor("#FFB347"))
BRAND_GRADIENT_COOL      = (ManimColor("#0F3460"), ManimColor("#6C63FF"))

# ── Opacity presets ───────────────────────────────────────────────────
OPACITY_FULL        = 1.0
OPACITY_HIGH        = 0.85
OPACITY_MEDIUM      = 0.6
OPACITY_LOW         = 0.3
OPACITY_GHOST       = 0.1
