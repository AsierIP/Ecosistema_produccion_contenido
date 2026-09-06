"""Small ASS drawing primitives shared by local comic productions."""
import math

HEADER = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Segoe UI Semibold,74,&H0000FFC8,&H009D00FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,6,2,5,80,80,200,1
Style: Graphic,Segoe UI Semibold,64,&H00FFFFFF,&H00FFFFFF,&H0020160C,&H8020160C,-1,0,0,0,100,100,0,0,1,4,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def timestamp(t):
    n = round(t*100)
    return f'{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}'

def rectangle(x,y,w,h):
    return f'm {x} {y} l {x+w} {y} {x+w} {y+h} {x} {y+h}'

def circle(cx,cy,r):
    k = r*.552285
    points=[cx+r,cy,cx+r,cy+k,cx+k,cy+r,cx,cy+r,cx-k,cy+r,cx-r,cy+k,cx-r,cy,cx-r,cy-k,cx-k,cy-r,cx,cy-r,cx+k,cy-r,cx+r,cy-k,cx+r,cy]
    v=[str(round(p,2)) for p in points]
    return 'm '+' '.join(v[:2])+' b '+' '.join(v[2:])

def ass_color(rgb):
    rgb=rgb.lstrip('#')
    return rgb[4:6]+rgb[2:4]+rgb[0:2]

class Canvas:
    def __init__(self): self.lines=[]
    def event(self,start,end,content,style='Graphic',layer=1):
        if end <= start: return
        self.lines.append(f'Dialogue: {layer},{timestamp(start)},{timestamp(end)},{style},,0,0,0,,{content}')
    def text(self,start,end,value,x,y,size=64,color='#FFFFFF',tags='',layer=2):
        self.event(start,end,r'{\pos('+f'{x},{y}'+r')\fs'+str(size)+r'\c&H'+ass_color(color)+'&'+tags+'}'+value,layer=layer)
    def draw(self,start,end,path,color='#081629',border=0,tags='',layer=1):
        self.event(start,end,r'{\an7\pos(0,0)\p1\c&H'+ass_color(color)+r'&\bord'+str(border)+r'\shad0'+tags+'}'+path+r'{\p0}',layer=layer)
    def save(self,path):
        path.write_text(HEADER+'\n'.join(self.lines)+'\n',encoding='utf-8-sig')
    def clock(self,start,end,cx=540,cy=840,r=242,fps=24):
        self.draw(start,end,circle(cx,cy,r+16),'#081629',3)
        self.draw(start,end,circle(cx,cy,r),'#F9FBFF')
        for i in range(12):
            theta=i*math.pi/6-math.pi/2
            inner=r-24 if i%3==0 else r-15
            ax,ay=cx+inner*math.cos(theta),cy+inner*math.sin(theta)
            bx,by=cx+(r-8)*math.cos(theta),cy+(r-8)*math.sin(theta)
            self.draw(start,end,f'm {ax:.2f} {ay:.2f} l {bx:.2f} {by:.2f}','#081629',4)
        for n in range(math.ceil((end-start)*fps)):
            a=start+n/fps; b=min(end,a+1/fps)
            minute=45*min((a-start)/(end-start),1)
            theta=minute*2*math.pi/60-math.pi/2
            tipx,tipy=cx+(r-48)*math.cos(theta),cy+(r-48)*math.sin(theta)
            self.draw(a,b,f'm {cx-8} {cy+6} l {tipx:.2f} {tipy:.2f} {cx+8} {cy-6}','#081629',3)
        self.draw(start,end,circle(cx,cy,14),'#FFD23F',3)
