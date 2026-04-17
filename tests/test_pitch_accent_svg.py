"""Tests for dark-background friendly pitch-accent SVG rendering."""

from __future__ import annotations

import unittest

from autofiller.pitch_accent import render_pitch_svg


class PitchAccentSvgTests(unittest.TestCase):
    """Validate SVG rendering uses contrast-safe styling primitives."""

    def test_render_pitch_svg_defaults_to_light_foreground(self) -> None:
        """Rendered SVG should expose a light foreground color for dark backgrounds."""
        svg = render_pitch_svg("あめ", "LH")

        self.assertIn('class="pitch"', svg)
        self.assertIn('style="color:#f5f5f5;"', svg)
        self.assertIn("fill:#f5f5f5", svg)
        self.assertIn("stroke:#f5f5f5", svg)

    def test_render_pitch_svg_uses_hollow_trailing_points(self) -> None:
        """Pattern points beyond mora count should render as hollow circles."""
        svg = render_pitch_svg("あ", "LHH")

        self.assertIn("fill:none;stroke:#f5f5f5", svg)

    def test_render_pitch_svg_light_theme(self) -> None:
        """Light theme should use dark foreground for white backgrounds."""
        svg = render_pitch_svg("あめ", "LH", theme="light")

        self.assertIn('style="color:#111111;"', svg)
        self.assertIn("fill:#111111", svg)


if __name__ == "__main__":
    unittest.main()
