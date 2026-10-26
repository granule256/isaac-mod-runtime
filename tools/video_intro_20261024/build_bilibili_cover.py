#!/usr/bin/env python3
"""用实机截图制作朴素封面与发布标题；不调用生成图片或发布服务。"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024/B站发布素材-20261024')
FONT = '/Applications/BCUT.app/Contents/Resources/Font/Source Han Sans CN Medium.ttf'
SOURCE = Path('/Users/kelinls/Movies/以撒pc模组兼容层介绍-配音字幕对齐-无字幕.mp4')
TITLE = '我让 Switch 版以撒用上了 PC 模组｜EID、GoodTrip 实机演示'


def safe_cover():
    target=OUT/'B站封面-4比3-安全布局.jpg'
    assert not target.exists(), '请另存新版本，不覆盖已有封面'
    image=Image.new('RGB',(1600,1200),'#E9DDC4')
    image=Image.blend(image,Image.effect_noise(image.size,12).convert('RGB'),0.025)
    draw=ImageDraw.Draw(image)
    boxes=[]
    def centered(y,text,size,color,bold=0):
        font=ImageFont.truetype(FONT,size)
        width=draw.textlength(text,font=font)
        x=round((1600-width)/2)
        box=draw.textbbox((x,y),text,font=font,anchor='lt',stroke_width=bold)
        assert 200<=box[0] and 150<=box[1] and box[2]<=1400 and box[3]<=1050
        draw.text((x,y),text,font=font,fill=color,anchor='lt',stroke_width=bold,stroke_fill=color)
        boxes.append({'文字':text,'边界':box})
    centered(180,'PC 模组兼容进度',28,'#686050')
    centered(240,'Switch 以撒',82,'#2B2722',2)
    centered(355,'PC 模组跑起来了',112,'#9B352D',3)
    draw.rounded_rectangle((1180,236,1340,292),radius=7,outline='#9B352D',width=2)
    font=ImageFont.truetype(FONT,28)
    draw.text((1218,248),'开发中',font=font,anchor='lt',fill='#9B352D')
    boxes.append({'文字':'开发中','边界':[1180,236,1340,292]})
    # 重排主机位置；不把旧横版简单铺满或拉伸。
    original=Image.open(OUT/'B站封面-推荐版.png').convert('RGB')
    device=original.crop((620,270,1580,750))
    image.paste(device,(320,500))
    boxes.append({'主体':'主机与屏幕（含阴影留白）','边界':[320,500,1280,980]})
    draw=ImageDraw.Draw(image)
    centered(994,'EID · GoodTrip · 控制台 · 跳舞',34,'#514A40')
    image.save(target,quality=95,subsampling=0)
    image.save(OUT/'B站封面-4比3-安全布局.png')
    image.resize((400,300),Image.Resampling.LANCZOS).save(OUT/'4比3封面缩略检查.jpg',quality=95)
    # 以下仅是跨场景裁切检查，不作为用户上传的封面版本。
    crops={'横向裁切检查':(0,150,1600,1050),'方形裁切检查':(200,0,1400,1200)}
    for name,rect in crops.items():
        for item in boxes:
            x0,y0,x1,y1=item.get('边界')
            assert rect[0]<=x0 and rect[1]<=y0 and x1<=rect[2] and y1<=rect[3]
        image.crop(rect).save(OUT/(name+'.jpg'),quality=95)
    result={'上传封面':str(target),'尺寸':[1600,1200],'比例':'4:3',
            '内容安全区':[200,150,1400,1050],'文字和主体边界':boxes,
            '已检验裁切':crops,'文件字节':target.stat().st_size,
            'SHA256':hashlib.sha256(target.read_bytes()).hexdigest(),
            '说明':'验证居中横向和方形裁切中的核心内容完整；裁切检查图仅供核验。'}
    (OUT/'4比3裁切核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='文字和主体边界'},ensure_ascii=False,indent=2))


def main():
    OUT.mkdir(exist_ok=True)
    master = OUT/'B站封面-推荐版.png'
    assert not master.exists(), '已有版本请另存，不覆盖用户封面'
    shot = OUT/'封面用实机画面.jpg'
    subprocess.run(['ffmpeg','-v','error','-ss','33','-i',str(SOURCE),
                    '-frames:v','1','-q:v','2','-y',str(shot)],check=True)
    image = Image.new('RGB',(1600,1000),'#E9DDC4')
    noise = Image.effect_noise(image.size,12).convert('RGB')
    image = Image.blend(image,noise,0.025).convert('RGBA')
    draw = ImageDraw.Draw(image)
    ink = '#2B2722'
    red = '#9B352D'
    boxes = []

    def text(x,y,string,size,color=ink,bold=0):
        font = ImageFont.truetype(FONT,size)
        bbox = draw.textbbox((x,y),string,font=font,anchor='lt',stroke_width=bold)
        assert bbox[0]>=40 and bbox[1]>=50 and bbox[2]<=1560 and bbox[3]<=950
        boxes.append({'text':string,'box':bbox})
        draw.text((x,y),string,font=font,fill=color,anchor='lt',stroke_width=bold,stroke_fill=color)

    text(72,92,'PC 模组兼容进度',30,'#686050')
    draw.rounded_rectangle((1380,82,1530,140),radius=8,outline=red,width=2)
    text(1410,94,'开发中',29,red)
    text(72,225,'Switch 以撒',82,ink,2)
    text(72,355,'PC 模组',136,red,3)
    text(72,520,'跑起来了',132,ink,3)
    text(76,738,'实机演示',36,'#585043')

    # 平面主机轮廓用于指明平台，屏幕内容全部来自项目实机。
    shadow = Image.new('RGBA',image.size)
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((650,317,1550,723),radius=47,fill=(38,29,17,55))
    image = Image.alpha_composite(image,shadow.filter(ImageFilter.GaussianBlur(14)))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((650,300,758,706),radius=48,fill='#3196A4')
    draw.rounded_rectangle((1442,300,1550,706),radius=48,fill='#C64A43')
    draw.rounded_rectangle((741,300,1459,706),radius=23,fill='#25282B')
    draw.rounded_rectangle((758,312,1442,694),radius=8,fill='#0D1012')
    gameplay = Image.open(shot).convert('RGBA').resize((650,366),Image.Resampling.LANCZOS)
    image.alpha_composite(gameplay,(775,320))
    draw = ImageDraw.Draw(image)

    def circle(cx,cy,r,fill):
        draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=fill)

    for x,y in [(700,410),(1500,545)]:
        circle(x,y,28,'#17292D')
        circle(x,y,21,'#2D393C')
    draw.rounded_rectangle((686,338,714,344),radius=2,fill='#19343A')
    for x,y in [(700,516),(679,537),(721,537),(700,558)]:
        circle(x,y,11,'#1C3338')
    for x,y in [(1500,379),(1477,402),(1523,402),(1500,425)]:
        circle(x,y,12,'#3B2627')
    draw.line((1488,340,1512,340),fill='#502B2A',width=5)
    draw.line((1500,328,1500,352),fill='#502B2A',width=5)
    draw.rounded_rectangle((688,622,711,644),radius=3,fill='#24414A')
    circle(1500,632,13,'#6D3331')
    text(752,756,'EID · GoodTrip · 控制台 · 跳舞',34,'#514A40')
    draw.line((72,860,1530,860),fill='#B7AA91',width=2)
    text(74,892,'以撒的结合：忏悔',30,'#514A40')
    text(1240,896,'项目介绍 / 实机画面',25,'#6C6353')

    image = image.convert('RGB')
    image.save(master)
    image.save(OUT/'B站封面-推荐版.jpg',quality=95,subsampling=0)
    image.crop((0,50,1600,950)).save(OUT/'B站封面-16比9.jpg',quality=95,subsampling=0)
    thumb = image.resize((400,250),Image.Resampling.LANCZOS)
    thumb.save(OUT/'封面缩略图检查.jpg',quality=95)
    (OUT/'发布标题.txt').write_text(TITLE+'\n\n备选：\n给 Switch 版以撒做了个 PC 模组兼容层，现在能跑哪些？\nSwitch 版以撒的 PC 模组兼容进度：EID、GoodTrip、控制台和跳舞\n')
    result = {'标题':TITLE,'主封面':str(OUT/'B站封面-推荐版.jpg'),
              '主封面尺寸':[1600,1000],'16比9尺寸':[1600,900],
              '素材来源':str(SOURCE),'取帧秒':33,'设计':'纸色底、深色大字、实机画面、平面主机轮廓、开发中标记',
              '文字边界':boxes,
              '素材帧SHA256':hashlib.sha256(shot.read_bytes()).hexdigest(),
              '封面字节数':(OUT/'B站封面-推荐版.jpg').stat().st_size}
    (OUT/'封面与标题制作记录.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='文字边界'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--safe-4-3',action='store_true',help='制作居中安全布局的4:3封面')
    args=parser.parse_args()
    safe_cover() if args.safe_4_3 else main()
