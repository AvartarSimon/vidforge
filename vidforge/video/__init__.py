"""Video tools that work on a finished clip rather than on a project segment.

Everything here takes an mp4 in and gives an mp4 out, so it is equally usable from the CLI,
from the web UI's 视频 section, and on footage that never goes through vidforge's pipeline.

    heads  — find the faces in a clip and cover each one with a picture (a cartoon head, a logo,
             a blurred disc): the practical way to put your own footage in a video without
             showing your face.
"""

from __future__ import annotations


class VideoToolError(RuntimeError):
    pass
