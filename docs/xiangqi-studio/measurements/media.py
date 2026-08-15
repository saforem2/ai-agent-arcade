from PIL import Image, ImageDraw, ImageFont
FONT="/System/Library/Fonts/STHeiti Medium.ttc"

def bits(ch,w,h):
    for px in range(max(w,h),max(w,h)*6):
        f=ImageFont.truetype(FONT,px)
        im=Image.new("L",(px*2,px*2),0)
        ImageDraw.Draw(im).text((px,px),ch,font=f,fill=255,anchor="mm")
        bb=im.getbbox()
        if bb and max(bb[2]-bb[0],bb[3]-bb[1])>=max(w,h)*3:
            c=im.crop(bb).resize((w,h),Image.LANCZOS).load()
            return [[c[x,y]>110 for x in range(w)] for y in range(h)]

BR=[0x01,0x08,0x02,0x10,0x04,0x20,0x40,0x80]
def braille(g,w,h):
    out=[]
    for cy in range(0,h,4):
        row=""
        for cx in range(0,w,2):
            v=0
            for i,(dx,dy) in enumerate([(0,0),(1,0),(0,1),(1,1),(0,2),(1,2),(0,3),(1,3)]):
                y,x=cy+dy,cx+dx
                if y<h and x<w and g[y][x]: v|=BR[i]
            row+=chr(0x2800+v)
        out.append(row)
    return out

QUAD={0:" ",1:"▘",2:"▝",3:"▀",4:"▖",5:"▌",6:"▞",7:"▛",8:"▗",9:"▚",10:"▐",11:"▜",12:"▄",13:"▙",14:"▟",15:"█"}
def quad(g,w,h):
    out=[]
    for cy in range(0,h,2):
        row=""
        for cx in range(0,w,2):
            v=0
            for i,(dx,dy) in enumerate([(0,0),(1,0),(0,1),(1,1)]):
                y,x=cy+dy,cx+dx
                if y<h and x<w and g[y][x]: v|=(1<<i)
            row+=QUAD[v]
        out.append(row)
    return out

def sextant(g,w,h):
    out=[]
    for cy in range(0,h,3):
        row=""
        for cx in range(0,w,2):
            v=0
            for i,(dx,dy) in enumerate([(0,0),(1,0),(0,1),(1,1),(0,2),(1,2)]):
                y,x=cy+dy,cx+dx
                if y<h and x<w and g[y][x]: v|=(1<<i)
            if v==0: row+=" "
            elif v==63: row+="█"
            else:
                n=v-1-(1 if v>21 else 0)-(1 if v>42 else 0)
                row+=chr(0x1FB00+n) if v not in (21,42) else ("▌" if v==21 else "▐")
        out.append(row)
    return out

for ch in ("車","將","象"):
    print(f"\n{'='*54}  {ch}")
    b=braille(bits(ch,14,16),14,16)
    q=quad(bits(ch,14,16),14,16)
    s=sextant(bits(ch,14,18),14,18)
    print("  BRAILLE 2x4 (gappy)      QUADRANT 2x2 (solid)     SEXTANT 2x3 (solid)")
    for i in range(max(len(b),len(q),len(s))):
        print(f"  {b[i] if i<len(b) else '':<24} {q[i] if i<len(q) else '':<24} {s[i] if i<len(s) else ''}")
