from PIL import Image, ImageDraw, ImageFont
FONT="/System/Library/Fonts/STHeiti Medium.ttc"
HARD=[("general","將"),("cannon","砲"),("elephant","象"),("horse","馬")]
def bits(ch,box):
    for px in range(box,box*6):
        f=ImageFont.truetype(FONT,px)
        im=Image.new("L",(px*2,px*2),0)
        ImageDraw.Draw(im).text((px,px),ch,font=f,fill=255,anchor="mm")
        bb=im.getbbox()
        if bb and max(bb[2]-bb[0],bb[3]-bb[1])>=box*3:
            c=im.crop(bb).resize((box,box),Image.LANCZOS).load()
            return ["".join("#" if c[x,y]>110 else "." for x in range(box)) for y in range(box)]
for box in (12,14,16):
    print(f"\n{'='*24} disc {box}x{box} {'='*24}")
    grids=[(l,bits(c,box)) for l,c in HARD]
    print("   " + "".join(f"{l:<{box+4}}" for l,_ in grids))
    for y in range(box):
        print("   " + "".join(g[y]+"    " for _,g in grids))
