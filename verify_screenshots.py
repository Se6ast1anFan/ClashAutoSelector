"""Offline end-to-end fixture check; writes annotated previews to verification/."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from vision import Vision
from core import choose, all_timeout


def main():
    engine = Vision()
    output = Path("verification")
    output.mkdir(exist_ok=True)
    for i in range(1,6):
        rgb = np.asarray(Image.open(f"{i}.png").convert("RGB"))
        found,complete,texts = engine.scan(rgb,"新加坡")
        button = engine.button(rgb,texts)
        best = choose(found)
        print(i,"cards",len(found),"complete",complete,"button",button,"best",(best.name,best.status) if best else None,flush=True)
        for c in found:
            print(" ",c.name,c.status,c.selected,c.reliable,flush=True)
        engine.preview(rgb,found,button).save(output / f"{i}.png")
        assert len(found) == 8, f"{i}: should detect eight Singapore cards"
        if i >= 3:
            assert best and "直连" in best.name and best.delay == 232, f"{i}: incorrect selection"
    original = Image.open("3.png").convert("RGB")
    for scale in [.75,1.25,1.5]:
        im = original.resize((round(original.width*scale),round(original.height*scale)))
        rgb = np.asarray(im)
        found,complete,texts = engine.scan(rgb,"新加坡")
        button = engine.button(rgb,texts)
        best = choose(found)
        print("scale",scale,"cards",len(found),"button",button,"best",best,flush=True)
        assert best and "直连" in best.name and best.delay == 232
    # Reflow the real cards into two and four columns, retaining the toolbar.
    source = np.asarray(original)
    cards = [source[y:y+70,x:x+404] for x,y in [(1099,636),(270,716),(684,716),(1099,716),(270,796),(684,796),(1099,796),(270,876)]]
    for cols in (2,4):
        canvas = Image.new("RGB",(max(1533,cols*414+280),236+((len(cards)+cols-1)//cols)*80),(30,31,39))
        canvas.paste(original.crop((0,0,1533,236)),(0,0))
        for n,card in enumerate(cards):
            canvas.paste(Image.fromarray(card),(270+(n%cols)*414,236+(n//cols)*80))
        rgb=np.asarray(canvas)
        found,complete,texts=engine.scan(rgb,"新加坡")
        best=choose(found)
        assert len(found)==8 and best and best.delay==232, f"{cols} column reflow failed"
        engine.button(rgb,texts)
        engine.preview(rgb,found).save(output/f"columns-{cols}.png")
        print("columns",cols,"passed",flush=True)
    # Keep real node titles/cards and replace only the right-hand status labels.
    original_candidates,_,_ = engine.scan(source,"新加坡")
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",18)
    for mixed in (False,True):
        im=original.copy()
        draw=ImageDraw.Draw(im)
        for n,c in enumerate(original_candidates):
            x,y,w,h=c.rect
            color=(23,66,114) if c.selected else (36,37,47)
            draw.rectangle((x+w-130,y+5,x+w-5,y+h-5),fill=color)
            draw.text((x+w-14,y+h/2),"Error" if mixed and n==0 else "Timeout",font=font,anchor="rm",fill=(255,69,58))
        found,complete,_=engine.scan(np.asarray(im),"新加坡")
        print("timeout fixture",mixed,"complete",complete,[(c.status,c.reliable) for c in found],flush=True)
        assert len(found)==8 and all_timeout(found,complete)==(not mixed)
        engine.preview(np.asarray(im),found).save(output/("mixed-error.png" if mixed else "all-timeout.png"))
    found,_,_=engine.scan(source,"不存在的节点关键词")
    assert not found
    print("ALL SCREENSHOT CHECKS PASSED",flush=True)


if __name__ == "__main__":
    main()
