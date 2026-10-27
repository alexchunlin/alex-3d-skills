"""cadlib: parametric, print-ready assembly helpers for headless Blender 5.1+.

    import sys; sys.path.insert(0, "<skill>/scripts")
    from cadlib import geom, features as F, asm, export, render, blend

See ../../SKILL.md for the conventions and the workflow.
"""
from . import geom, features, asm, export, render  # noqa: F401


def __getattr__(name):
    # blend loads numpy and openvdb: only for scripts that use it (`from cadlib import blend`, or cadlib.blend)
    if name == "blend":
        import importlib
        return importlib.import_module(".blend", __name__)   # `from . import blend` here would recurse into __getattr__
    raise AttributeError("module 'cadlib' has no attribute %r" % name)
