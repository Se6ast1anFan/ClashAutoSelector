"""Packaged offline OCR smoke test, invoked only with --self-test OUTPUT.json."""
import json
from pathlib import Path
import socket


def run(destination):
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    from vision import Vision
    def offline(*args, **kwargs):
        raise RuntimeError("Self-test prohibits network access")
    socket.socket.connect = offline
    report = {"ok":False,"network":"disabled"}
    try:
        engine = Vision()
        im = Image.new("RGB",(600,160),(36,37,47))
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",32)
        ImageDraw.Draw(im).text((15,35),"新加坡 232 Timeout",font=font,fill="white")
        _,_,texts = engine.scan(np.asarray(im),"新加坡")
        recognized = " ".join(t[2] for t in texts)
        assert "232" in recognized and "新加坡" in recognized, recognized
        assert engine.template is not None
        report.update(ok=True,recognized=recognized)
    except Exception as exc:
        report["error"] = str(exc)
    Path(destination).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0 if report["ok"] else 1
