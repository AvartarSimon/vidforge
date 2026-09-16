"""vidforge — script-to-video assembly line.

Pipeline: project.json -> TTS per segment (edge-tts, word timings) -> SRT
-> Ken Burns clip per segment (ffmpeg zoompan) -> concat -> BGM mix
-> optional burned-in subtitles -> thumbnail.
"""

__version__ = "0.1.0"
