from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph,Table,TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
import math

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'report/Mandol近重复记忆合并_演示汇报.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('Hei','C:/Windows/Fonts/simhei.ttf'))
pdfmetrics.registerFont(TTFont('Song','C:/Windows/Fonts/simsun.ttc',subfontIndex=0))
W,H=960,540
INK='#1C3344'; MUTED='#536A77'; ACCENT='#117F83'; LIGHT='#EDF5F5'; LINE='#D9E4E8'
c=canvas.Canvas(str(OUT),pagesize=(W,H))
c.setTitle('Mandol 近重复记忆合并改进 - 初步课堂汇报')
c.setAuthor('课程大作业')
n=0

def text(x,top,w,h,s,size=22,color=INK,font='Hei',leading=None):
    p=Paragraph(s,ParagraphStyle('p',fontName=font,fontSize=size,leading=leading or size*1.4,textColor=colors.HexColor(color),wordWrap='CJK'))
    _,ph=p.wrap(w,h)
    assert ph<=h+0.1, f'slide {n}: text overflow {s[:40]}: {ph}>{h}'
    p.drawOn(c,x,H-top-ph)

def line(x1,y1,x2,y2,color=LINE,width=1):
    c.setStrokeColor(colors.HexColor(color));c.setLineWidth(width)
    c.line(x1,H-y1,x2,H-y2)

def arrow(x1,y1,x2,y2):
    line(x1,y1,x2,y2,ACCENT,1.8)
    a=math.atan2(y2-y1,x2-x1)
    for off in [-.5,.5]:
        line(x2,y2,x2-9*math.cos(a+off),y2-9*math.sin(a+off),ACCENT,1.8)

def start(title,source=''):
    global n
    if n:c.showPage()
    n+=1
    c.setFillColor(colors.white);c.rect(0,0,W,H,fill=1,stroke=0)
    text(52,30,850,22,'面向对象程序设计 · 大作业阶段汇报',13,MUTED)
    text(52,76,860,60,title,32)
    line(52,145,908,145)
    text(886,507,40,20,f'{n:02}',12,MUTED)
    if source:text(52,501,810,30,source,10.5,MUTED,font='Song',leading=14)

def bullet(top,label,body):
    text(55,top,34,34,'•',23,ACCENT)
    text(88,top,810,36,label,23)
    text(88,top+41,805,66,body,20,MUTED)

def diagram_box(x,top,w,h,label,body=''):
    c.setFillColor(colors.HexColor(LIGHT));c.setStrokeColor(colors.HexColor('#B6D1D2'))
    c.roundRect(x,H-top-h,w,h,5,fill=1,stroke=1)
    if body:
        text(x+13,top+13,w-26,32,label,21,INK)
        text(x+13,top+49,w-26,h-53,body,17,MUTED)
    else:text(x+13,top+16,w-26,h-20,label,21)

def table(top,rows,widths,size=20):
    data=[[Paragraph(v,ParagraphStyle('cell',fontName='Hei',fontSize=size,leading=size*1.35,textColor=colors.HexColor(INK),wordWrap='CJK')) for v in row] for row in rows]
    t=Table(data,colWidths=widths)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor(LIGHT)),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12),('LINEBELOW',(0,0),(-1,-1),.6,colors.HexColor(LINE))]))
    _,h=t.wrap(856,350)
    assert top+h<493, f'table slide {n} overflow {h}'
    t.drawOn(c,52,H-top-h)
    return top+h

start('')
c.setFillColor(colors.white);c.rect(0,0,W,H,fill=1,stroke=0)
text(64,63,820,32,'面向对象程序设计课程大作业',20,MUTED)
text(64,160,825,132,'Mandol 智能体记忆系统<br/>近重复记忆合并的初步分析',40,INK,leading=58)
text(67,327,810,60,'超长记忆增强方向：代码阅读、改进思路和目前进度',23,MUTED)

start('为什么想改进记忆合并')
table(174,[['记录','内容'],['A','用户周五去上海参加会议。'],['B','用户周五去上海参加会议，周日返回。'],['C','如果请假获批，用户周五去上海。']],[95,761],21)
text(57,417,845,65,'想减少重复内容，但也要留下新增的信息和原始来源。',24,ACCENT)

start('我对 Mandol 的基本理解')
text(57,178,845,65,'Mandol 负责保存和查找记忆，应用再把查到的内容交给模型生成回答。',23)
diagram_box(55,267,235,92,'写入与存储','基础记忆、向量、空间、图')
diagram_box(362,267,235,92,'构建高阶记忆','摘要、情景、实体关系')
diagram_box(669,267,235,92,'检索与返回','召回、筛选、上下文')
arrow(291,312,360,312);arrow(598,312,667,312)
text(58,405,845,70,'先把范围放在 L1 摘要去重上，复用原来的存储和检索。',24,ACCENT)

start('读代码时先关注这几个对象')
diagram_box(59,185,386,93,'SemanticGraph','管理节点和关系，持有 SemanticMap')
diagram_box(59,330,386,93,'SemanticMap','管理记忆内容、空间与检索索引')
diagram_box(557,185,345,93,'MemoryUnit','UID、内容、元数据、向量')
diagram_box(557,330,345,93,'MemorySpace','记忆 UID 归属和子空间')
arrow(252,279,252,329)
arrow(446,365,500,365);arrow(500,365,500,231);arrow(500,231,556,231)
arrow(500,376,556,376)

start('准备改在原流程的哪个位置')
steps=[('L0','基础记忆'),('L1','会话摘要'),('去重','准备修改这里'),('L2','进一步汇总')]
for i,(label,body) in enumerate(steps):
    x=55+i*221
    diagram_box(x,207,190,101,label,body)
    if i<3:arrow(x+192,256,x+219,256)
text(59,351,844,55,'去重后的 L1 会继续生成 L2，之后由原来的流程写入系统。',23)

start('原来的去重代码是怎样处理的')
text(57,175,845,66,'先按摘要类型分组，将每条摘要的前 500 个字符交给模型判断。',23)
text(70,267,810,95,'merged_from = ["A", "B"]<br/>kept_ids.add(merged_from[0])',25,ACCENT,leading=40)
text(57,384,845,73,'这段代码留下第一项的原文，没有采用模型返回的合并文本，也没有汇总其他条目的来源。',22)

start('哪些内容可以合并，哪些先保留')
table(172,[['情况','第一版准备怎样处理'],['同一事实的重复表达','保留一条，并汇总来源。'],['一条包含另一条的信息','先检查条件是否一致，再选择信息更全的一条。'],['否定、数字、时间或条件不同','保留两条，避免把不同事实混在一起。'],['无法确认或返回格式异常','先不合并，记录原因。']],[268,588],20)

start('目前考虑的处理步骤')
names=[('找候选内容','CandidateFinder'),('判断能否合并','MergeJudge'),('记录合并决定','MergePlan'),('检查后再写入','接回原流程')]
for i,(label,body) in enumerate(names):
    x=55+i*221
    diagram_box(x,202,190,100,label,body)
    if i<3:arrow(x+192,251,x+219,251)
text(59,345,845,92,'先用已有文本作为结果，记下合并了谁、来源是什么、为什么合并。<br/>图中是准备划分的职责，当前原型还集中在一个处理类里。',22,leading=35)

start('一个希望实现的合并例子')
text(60,175,820,35,'输入',22,ACCENT)
text(60,220,825,101,'A：周五去上海  [来源 a]<br/>B：周五去上海；周日返回  [来源 b]',25,leading=44)
line(60,331,899,331)
text(60,360,820,30,'确认 B 包含 A 的信息后，希望得到',21,ACCENT)
text(60,405,830,72,'B：周五去上海；周日返回<br/>来源：[a, b]    合并成员：[A, B]',24,leading=36)

start('目前做过哪些检查')
table(172,[['检查的事情','观察到的结果'],['合并后能否保存','通过原写入流程入图，来源信息也能保存。'],['补充信息能否查到','FAISS、BM25 能查到；也检查了冷数据换出和删除。'],['重新打开是否一致','关闭图资源，再用新进程加载，数据和检索结果一致。']],[252,604],20)

start('目前的进度和接下来要做的事')
text(58,174,820,35,'目前做到的',23,ACCENT)
text(58,222,840,64,'读了相关代码，做了一个保守合并原型；也检查了入图、检索和保存恢复。',23)
text(58,316,820,35,'还需要继续做',23,ACCENT)
text(58,362,840,90,'补齐主体字段，处理条件和时间差异，再接入完整构建流程；<br/>用复核过的数据检查合并有没有丢信息，以及实际问答效果。',23,leading=35)
c.save()
print(OUT)
