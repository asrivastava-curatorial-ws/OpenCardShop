"""OpenCardShop: a native, offline greeting-card editor, with optional CardShop Plus content."""

__version__ = "1.3.1"

try:
    from PIL import Image as _Image
except ImportError:  # main.py reports the missing dependency with installation advice
    _Image = None

if _Image is not None and not hasattr(_Image, "Resampling"):
    # Pillow 9.0 (Ubuntu 22.04) has the Pillow 9.1+ enums only as module constants.
    from types import SimpleNamespace as _Names
    for _enum, _names in (("Resampling", ("NEAREST", "BOX", "BILINEAR", "HAMMING", "BICUBIC", "LANCZOS")),
                          ("Transform", ("AFFINE", "EXTENT", "PERSPECTIVE", "QUAD", "MESH")),
                          ("Transpose", ("FLIP_LEFT_RIGHT", "FLIP_TOP_BOTTOM", "ROTATE_90", "ROTATE_180",
                                         "ROTATE_270", "TRANSPOSE", "TRANSVERSE"))):
        setattr(_Image, _enum, _Names(**{name: getattr(_Image, name) for name in _names}))
