"""Offline OCR and geometry recognition for the supplied dark Clash Verge UI."""
from pathlib import Path
import sys
import re
import cv2
import numpy as np
from core import Candidate


def resource(name):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets" / name


class Vision:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        self.template = cv2.imdecode(np.fromfile(resource("speed.png"), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)

    def cards(self, rgb):
        masks = []
        for color in [(36, 37, 47), (23, 66, 114)]:
            mask = (np.max(np.abs(rgb.astype(np.int16) - color), axis=2) < 5).astype(np.uint8) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w >= 110 and 30 <= h <= rgb.shape[0] * .18 and w / h > 2.4 and cv2.contourArea(contour) / (w*h) > .80:
                    masks.append((x, y, w, h))
        # Red instructional boxes in the supplied examples can split a card.
        # Rejoin fragments only when their combined width matches a normal card.
        typical = float(np.median([r[2] for r in masks])) if masks else 0
        merged = []
        for item in sorted(set(masks), key=lambda r: (r[1], r[0])):
            if merged:
                x,y,w,h = merged[-1]
                xx,yy,ww,hh = item
                combined = xx+ww-x
                if abs(y-yy) <= 3 and abs(h-hh) <= 4 and 0 <= xx-x-w <= 12 and .85*typical <= combined <= 1.12*typical:
                    merged[-1] = (x,min(y,yy),combined,max(h,hh))
                    continue
            merged.append(item)
        return merged

    def scan(self, rgb, keyword):
        cards = self.cards(rgb)
        typical_height = float(np.median([r[3] for r in cards])) if cards else 70
        factor = float(np.clip(70/max(1,typical_height),.4,3.0))
        if abs(factor-1) < .01:
            factor=1.0
        working = cv2.resize(rgb,None,fx=factor,fy=factor,interpolation=cv2.INTER_CUBIC) if factor != 1 else rgb
        result, _ = self.ocr(cv2.cvtColor(working, cv2.COLOR_RGB2BGR))
        texts = []
        boxes = {}
        for box, value, confidence in result or []:
            points = np.array(box)/factor
            entry = (points[:, 0].mean(), points[:, 1].mean(), value.strip(), float(confidence))
            texts.append(entry)
            boxes[entry] = points
        candidates = []
        complete = True
        for x, y, w, h in cards:
            inside = [t for t in texts if x <= t[0] <= x+w and y <= t[1] <= y+h]
            names = [t for t in inside if t[0] < x+w*.80 and t[1] < y+h*.52 and keyword.casefold() in t[2].casefold()]
            if not names:
                # An unreadable title may hide another matching node: forbid all-timeout retry.
                if not any(t[0] < x+w*.80 and t[1] < y+h*.52 and t[3] >= .70 for t in inside):
                    complete = False
                continue
            title = max(names, key=lambda t: t[3])
            states = [t for t in inside if t[0] > x+w*.78]
            state = max(states, key=lambda t: t[3]) if states else None
            patch = rgb[y:y+h, x:x+w]
            blue = np.mean(np.max(np.abs(patch.astype(np.int16) - (23, 66, 114)), axis=2) < 8) > .35
            reliable = title[3] >= .70 and bool(state and state[3] >= .70)
            if state and re.fullmatch(r"[1-9]\d{0,5}(?:\s*ms)?",state[2],re.I):
                # Small coloured digits score lower than long words in this OCR
                # model. Require agreement with a second, enlarged inverted crop.
                points=boxes[state]
                left=max(0,int(points[:,0].min())-2)
                top=max(0,int(points[:,1].min())-2)
                right=min(rgb.shape[1],int(points[:,0].max())+3)
                bottom=min(rgb.shape[0],int(points[:,1].max())+3)
                crop=cv2.cvtColor(255-cv2.resize(rgb[top:bottom,left:right],None,fx=2,fy=2),cv2.COLOR_RGB2BGR)
                reread,_=self.ocr.text_recognizer([crop])
                same=bool(reread and re.sub(r"\s+","",reread[0][0]).casefold()==re.sub(r"\s+","",state[2]).casefold() and float(reread[0][1])>=.55)
                reliable=title[3]>=.70 and state[3]>=.60 and same
            candidates.append(Candidate(title[2], state[2] if state else "", (x,y,w,h), blue,reliable))
        # Every OCR keyword occurrence inside the card area must map to a detected card.
        grid_top = min((r[1] for r in cards), default=rgb.shape[0])
        if any(keyword.casefold() in t[2].casefold() and t[1] >= grid_top and
               not any(c.rect[0] <= t[0] <= c.rect[0]+c.rect[2] and c.rect[1] <= t[1] <= c.rect[1]+c.rect[3] for c in candidates)
               for t in texts):
            complete = False
        return candidates, complete, texts

    def button(self, rgb, texts):
        page = any("代理组" in t[2] for t in texts) and any("Selector" in t[2] or "节点选择" in t[2] for t in texts)
        if not page:
            raise RuntimeError("未识别到截图所示的代理节点页面")
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        best = (-1, None)
        # Toolbar lies above the first card row; exclude the node grid.
        cards = self.cards(rgb)
        bottom = min((r[1] for r in cards), default=int(rgb.shape[0]*.35))
        area = gray[:bottom]
        for scale in np.linspace(.55, 2.5, 60):
            template = cv2.resize(self.template, None, fx=scale, fy=scale)
            h, w = template.shape
            if h >= area.shape[0] or w >= area.shape[1]:
                continue
            _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED))
            if score > best[0]:
                best = score, (loc[0]+w//2, loc[1]+h//2)
        if best[0] < .78:
            raise RuntimeError(f"测速按钮定位置信度不足（{best[0]:.2f}）")
        return best[1]

    @staticmethod
    def preview(rgb, candidates, button=None):
        from PIL import Image, ImageDraw, ImageFont
        im = Image.fromarray(rgb)
        draw = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
        except OSError:
            font = ImageFont.load_default()
        for c in candidates:
            x,y,w,h = c.rect
            draw.rectangle((x,y,x+w,y+h), outline="lime" if c.reliable else "orange", width=3)
            draw.text((x+4,y+4), f"{c.name}: {c.status or '未识别'}", font=font, fill="yellow", stroke_width=1, stroke_fill="black")
        if button:
            x,y = button
            draw.ellipse((x-16,y-16,x+16,y+16), outline="red", width=3)
        return im
