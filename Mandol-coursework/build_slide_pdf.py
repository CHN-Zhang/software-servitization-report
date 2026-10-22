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
    text(52,30,850,22,'面向对象程序设计 · 第 8/9 周阶段汇报',13,MUTED)
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
c.setFillColor(colors.HexColor(INK));c.rect(0,0,W,H,fill=1,stroke=0)
text(64,63,820,32,'面向对象程序设计 / 超长记忆增强',19,'#9CD4D1')
text(64,160,825,132,'Mandol<br/>近重复记忆合并改进',44,'#FFFFFF',leading=58)
text(67,327,810,60,'目标系统理解、问题分析与初步方案',25,'#D5E5EC')
text(67,432,820,60,'第 8/9 周初步汇报    |    2026.10.23',16,'#B2C7D3',leading=25)

start('为什么想改进记忆合并')
table(174,[['记录','内容'],['A','用户周五去上海参加会议。'],['B','用户周五去上海参加会议，周日返回。'],['C','如果请假获批，用户周五去上海。']],[95,761],21)
text(57,417,845,65,'想减少重复内容，但也要留下新增的信息和原始来源。',24,ACCENT)

start('Mandol 在应用中负责什么','来源：README_PYPI.md；src/mandol/ 下的核心与构建模块')
text(57,178,845,65,'Mandol 负责保存和查找记忆，应用再把查到的内容交给模型生成回答。',23)
diagram_box(55,267,235,92,'写入与存储','基础记忆、向量、空间、图')
diagram_box(362,267,235,92,'构建高阶记忆','摘要、情景、实体关系')
diagram_box(669,267,235,92,'检索与返回','召回、筛选、上下文')
arrow(291,312,360,312);arrow(598,312,667,312)
text(58,405,845,70,'这次主要考虑改进 L1 摘要生成之后的去重处理。',24,ACCENT)

start('几个核心对象的分工','来源：core/memory_unit.py、memory_space.py、semantic_map.py、semantic_graph.py')
diagram_box(59,185,386,93,'SemanticGraph','管理节点和关系，持有 SemanticMap')
diagram_box(59,330,386,93,'SemanticMap','管理记忆内容、空间与检索索引')
diagram_box(557,185,345,93,'MemoryUnit','UID、内容、元数据、向量')
diagram_box(557,330,345,93,'MemorySpace','记忆 UID 归属和子空间')
arrow(252,279,252,329)
arrow(446,365,500,365);arrow(500,365,500,231);arrow(500,231,556,231)
arrow(500,376,556,376)
text(59,451,835,30,'图中的箭头表示持有和管理关系。',18,MUTED)

start('准备改在原流程的哪个位置','来源：auto_builder/high_level_memory.py 的 _build_hierarchical()')
steps=[('L0','基础记忆'),('L1','会话摘要'),('去重','准备修改这里'),('L2','进一步汇总')]
for i,(label,body) in enumerate(steps):
    x=55+i*221
    diagram_box(x,207,190,101,label,body)
    if i<3:arrow(x+192,256,x+219,256)
text(59,351,844,55,'去重后的 L1 会继续生成 L2，之后由原来的流程写入系统。',23)
text(59,420,840,55,'保存一条 MemoryUnit，并不等于已经完成摘要和其他高阶记忆的构建。',20,MUTED)

start('现有 L1 去重怎样处理','来源：auto_builder/hierarchical_builder.py 的 deduplicate_l1()，固定提交 6d7af4f')
text(57,175,845,66,'先按摘要类型分组，将每条摘要的前 500 个字符交给模型判断。',23)
text(70,267,810,95,'merged_from = ["A", "B"]<br/>kept_ids.add(merged_from[0])',25,ACCENT,leading=40)
text(57,384,845,94,'这段代码保留组内第一项的原文，没有采用模型返回的合并文本，也没有把其他条目的来源一起保存下来。',22)

start('哪些内容可以合并，哪些先保留')
table(172,[['情况','第一版准备怎样处理'],['同一事实的重复表达','保留一条，并汇总来源。'],['一条包含另一条的信息','先检查条件是否一致，再选择信息更全的一条。'],['否定、数字、时间或条件不同','保留两条，避免把不同事实混在一起。'],['无法确认或返回格式异常','先不合并，记录原因。']],[268,588],20)

start('初步方案：先判断是否能合并')
names=[('CandidateFinder','组织候选'),('MergeJudge','判断关系'),('MergePlan','记录决策'),('校验与适配','接回原流程')]
for i,(label,body) in enumerate(names):
    x=55+i*221
    diagram_box(x,202,190,100,label,body)
    if i<3:arrow(x+192,251,x+219,251)
text(59,345,845,92,'记录哪些条目被合并、留下哪条内容，以及来源、会话和判断理由。<br/>第一版先选用已有文本，暂时不让模型重新写摘要。',22,leading=35)
text(59,449,840,28,'目前先这样划分职责，具体接口还需要在实现时调整。',17,MUTED)

start('一个希望实现的合并例子')
text(60,175,820,35,'输入',22,ACCENT)
text(60,220,825,101,'A：周五去上海  [来源 a]<br/>B：周五去上海；周日返回  [来源 b]',25,leading=44)
line(60,331,899,331)
text(60,360,820,30,'确认 B 包含 A 的信息后，希望得到',21,ACCENT)
text(60,405,830,72,'B：周五去上海；周日返回<br/>来源：[a, b]    合并成员：[A, B]',24,leading=36)

start('当前进展与后续安排','参考：课程大作业说明第1-3页；官方仓库 github.com/AgentCombo/Mandol；固定提交 6d7af4f')
text(58,174,820,35,'已经完成',23,ACCENT)
text(58,222,840,64,'阅读主要源码，梳理对象和流程，找到 L1 去重的位置，整理初步方案。',23)
text(58,316,820,35,'接下来准备做',23,ACCENT)
text(58,362,840,90,'继续完善判断规则，把合并功能接入原流程；<br/>再检查信息有没有丢失、来源是否完整，以及检索效果和处理成本。',23,leading=35)
text(58,465,840,28,'当前仍是阶段性初稿，完整功能接入和系统验证尚未完成。',17,MUTED)
c.save()
print(OUT)
