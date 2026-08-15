from PIL import Image, ImageDraw, ImageFont
import sys

FONTS = {
    "STHeiti-Med": "/System/Library/Fonts/STHeiti Medium.ttc",
    "HiraginoGB":  "/System/Library/Fonts/Hiragino Sans GB.ttc",
}
# (label, traditional, simplified)
PIECES = [
    ("chariot",  "車", "车"),
    ("horse",    "馬", "马"),
    ("cannon",   "砲", "炮"),
    ("general",  "將", "将"),
    ("advisor",  "士", "士"),
    ("elephant", "象", "象"),
    ("soldier",  "卒", "卒"),
]
RED = [("general","帥","帅"),("advisor","仕","仕"),("elephant","相","相"),
       ("chariot","俥","车"),("horse","傌","马"),("cannon","炮","炮"),("soldier","兵","兵")]

def raster(ch, font_path, size, box):
    best = None
    for px in range(box, box*6):
        try: f = ImageFont.truetype(font_path, px)
        except Exception: return None
        img = Image.new("L", (px*2, px*2), 0)
        d = ImageDraw.Draw(img)
        d.text((px//2, px//2), ch, font=f, fill=255, anchor="mm")
        bb = img.getbbox()
        if not bb: continue
        w, h = bb[2]-bb[0], bb[3]-bb[1]
        if max(w, h) >= box*3:
            crop = img.crop(bb).resize((box, box), Image.LANCZOS)
            best = crop
            break
    if best is None: return None
    px_ = best.load()
    rows = []
    for y in range(box):
        rows.append("".join("#" if px_[x, y] > 96 else "." for x in range(box)))
    return rows

def ink(rows):
    tot = sum(r.count("#") for r in rows)
    return tot / (len(rows)*len(rows[0]))

box = int(sys.argv[1]) if len(sys.argv) > 1 else 10
fp = FONTS[sys.argv[2]] if len(sys.argv) > 2 else FONTS["STHeiti-Med"]
print(f"=== box {box}x{box}  font {sys.argv[2] if len(sys.argv)>2 else 'STHeiti-Med'} ===")
for label, trad, simp in PIECES:
    rt, rs = raster(trad, fp, box, box), raster(simp, fp, box, box)
    if not rt or not rs: 
        print(f"{label}: RASTER FAIL"); continue
    print(f"\n{label:9s}  TRAD {trad} (ink {ink(rt):.0%})        SIMP {simp} (ink {ink(rs):.0%})")
    for a, b in zip(rt, rs):
        print(f"           {a}          {b}")
