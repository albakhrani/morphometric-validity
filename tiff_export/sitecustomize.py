"""Co-emit a TIFF beside every PDF a figure generator writes.

Why a shim rather than editing the generators. The seven generators write
their output through matplotlib's Figure.savefig, but each builds its own
filename and its own extension list, so adding TIFF to all of them means
seven edits that then have to be kept in step with the figsize calibration.
Wrapping savefig catches every call site at once and leaves the generators
untouched.

Why this is an EXPORT and not a conversion. The TIFF is rendered from the
live Figure object with the same bbox and padding as the PDF, at a dpi
chosen for print. Rasterising the finished PDF instead would resample
artwork that has already been laid out, which is the thing the resolution
checker exists to catch.

Python imports sitecustomize automatically at startup when it is importable,
so putting this directory on PYTHONPATH is enough; nothing has to call it.

    PYTHONPATH=tiff_export FIG_TIFF_DPI=600 python figure5_merged.py ...

FIG_TIFF_DPI unset means the shim does nothing at all, so a normal run is
completely unaffected.
"""
import os

_DPI = os.environ.get("FIG_TIFF_DPI")

if _DPI:
    try:
        import matplotlib.figure

        _DPI = float(_DPI)
        _orig = matplotlib.figure.Figure.savefig
        _busy = set()

        def savefig(self, fname, **kw):
            out = _orig(self, fname, **kw)
            try:
                name = os.fspath(fname)
            except TypeError:
                return out                      # a buffer, not a path
            if not name.lower().endswith(".pdf") or id(self) in _busy:
                return out
            tif = name[:-4] + ".tif"
            _busy.add(id(self))
            try:
                # Same bbox and padding as the vector master, so the TIFF
                # covers exactly the same artwork area; only dpi differs.
                kw2 = {k: v for k, v in kw.items() if k != "dpi"}
                kw2.setdefault("facecolor", "white")
                _orig(self, tif, dpi=_DPI, **kw2)
            finally:
                _busy.discard(id(self))
            return out

        matplotlib.figure.Figure.savefig = savefig
    except Exception:
        # A shim that breaks a build is worse than no shim. Never fatal.
        pass
