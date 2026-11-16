"""vidforge — script-to-video assembly line.

Pipeline: project.json -> TTS per segment (edge-tts, word timings) -> SRT
-> Ken Burns clip per segment (ffmpeg zoompan) -> concat -> BGM mix
-> optional burned-in subtitles -> thumbnail.
"""

__version__ = "0.4.0"


def _trust_store() -> None:
    """python.org's macOS installer ships OpenSSL with no CA bundle until "Install Certificates"
    is run by hand, so every https download (pictures, hot lists, models) fails with
    CERTIFICATE_VERIFY_FAILED. Pointing OpenSSL at certifi's bundle fixes it for urllib too.
    Only when nothing is configured: a corporate proxy's own bundle must win."""
    import os
    import ssl
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return
    paths = ssl.get_default_verify_paths()
    if (paths.cafile and os.path.exists(paths.cafile)) or (paths.capath and os.path.isdir(paths.capath) and os.listdir(paths.capath)):
        return
    try:
        import certifi
    except ImportError:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()


_trust_store()
