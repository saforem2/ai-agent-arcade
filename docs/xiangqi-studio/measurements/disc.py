from PIL import Image, ImageDraw, ImageFont
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
BOX = 10
SET = [("chariot","車"),("horse","馬"),("cannon","砲"),("general","將"),
       ("advisor","士"),("elephant","象"),("soldier","卒")]

def glyph_bits(ch, box, inset=2):
    inner = box - inset
    for px in range(inner, inner*6):
        f = ImageFont.truetype(FONT, px)
        img = Image.new("L", (px*2, px*2), 0)
        ImageDraw.Draw(img).text((px, px), ch, font=f, fill=255, anchor="mm")
        bb = img.getbbox()
        if bb and max(bb[2]-bb[0], bb[3]-bb[1]) >= inner*3:
            c = img.crop(bb).resize((inner, inner), Image.LANCZOS).load()
            return [[c[x,y] > 110 for x in range(inner)] for y in range(inner)], inner
    return None, inner

def disc_mask(box):
    r = box/2.0; cx = cy = (box-1)/2.0
    return [[((x-cx)**2 + (y-cy)**2) <= (r-0.25)**2 for x in range(box)] for y in range(box)]

for label, ch in SET:
    g, inner = glyph_bits(ch, BOX)
    d = disc_mask(BOX)
    off = (BOX - inner)//2
    rows = []
    for y in range(BOX):
        row = ""
        for x in range(BOX):
            on = d[y][x]
            gy, gx = y-off, x-off
            if on and 0 <= gy < inner and 0 <= gx < inner and g[gy][gx]:
                on = False           # knock the character OUT of the disc
            row += "#" if on else "."
        rows.append(row)
    ink = sum(r.count("#") for r in rows)/(BOX*BOX)
    print(f"\n{label}  {ch}   solid ink {ink:.0%}")
    for r in rows: print("   " + r)
