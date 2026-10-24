"""cadlib: parametric, print-ready assembly helpers for headless Blender 5.1+.

    import sys; sys.path.insert(0, "<skill>/scripts")
    from cadlib import geom, features as F, asm, export, render

See ../../SKILL.md for the conventions and the workflow.
"""
from . import geom, features, asm, export, render  # noqa: F401
