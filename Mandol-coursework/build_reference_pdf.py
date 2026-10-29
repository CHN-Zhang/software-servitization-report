"""Companion notes for the slide PDF. Also exports editable Markdown."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "report"
OUT.mkdir(exist_ok=True)
pdfmetrics.registerFont(TTFont("RefBody", "C:/Windows/Fonts/simsun.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("RefHead", "C:/Windows/Fonts/simhei.ttf"))

PAGES = [
    ("逐页讲解参考：第 1—4 页", [
        ("这份资料怎么用", "这是演示稿的配套笔记，适合汇报前熟悉内容，或者回答问题时查阅。正文沿用学生阶段汇报的口吻，不需要逐字照读。对应演示稿共11页；没有在这里重新做一轮实验。"),
        ("第1页：选题介绍", "我选的是 Mandol 的超长记忆增强方向。目前把范围缩小到 L1 摘要的近重复合并，主要想处理‘内容看起来相近，但又不能直接删掉’的情况。这次讲系统理解、初步方案和已完成的连接验证。"),
        ("第2页：为什么考虑这个问题", "A和B都说周五去上海，但B还说周日返回。如果简单留下A，返回日期就没有了。C带有请假获批的条件，与确定的行程也不能直接当成同一件事。这里是需求示例，不是实验数据。"),
        ("第3页：系统负责什么", "Mandol负责组织、存储和检索记忆，外部应用再用这些记忆生成回答。高阶记忆包括分层摘要、情景和实体关系，本次只优先处理分层摘要的去重，不准备重做整个系统。"),
        ("第4页：核心对象", "MemoryUnit是一条记忆，MemorySpace记录逻辑归属；SemanticMap管理内容和索引，SemanticGraph在其上管理节点和关系。图中的箭头不是继承。空间主要保存UID归属，不能理解成每个空间都复制了完整文本和向量。"),
    ]),
    ("逐页讲解参考：第 5—8 页", [
        ("第5页：接入位置", "先按会话生成L1，经过可选去重，再聚合L2并写入系统。我准备优先修改写入前的L1结果列表，这样可以先不处理已有历史图的节点迁移。保存基础记忆不等于已经完成所有高阶构建。"),
        ("第6页：源码中观察到的行为", "deduplicate_l1()先按摘要类型分组，提交每条摘要前500个字符。模型返回合并组以后，后处理保留组里第一个ID对应的原结果，没有采用result中的融合文本，也没有在这里汇总其他项的来源。说的是这段代码的行为，不能直接推断真实模型经常造成损失。"),
        ("第7页：先确定处理边界", "等价重复可以合并；一条信息更全时，也要先确认主体、时间和条件一致。数字、否定和例外可能改变事实。不能确认或返回格式不对时，先保留输入比贸然删除更稳妥，但也会减少压缩机会。"),
        ("第8页：对象职责", "CandidateFinder负责组织候选，MergeJudge判断关系，MergePlan记录留下谁、合并谁以及来源，校验与适配负责接回原流程。这些是设计中的职责，还没有全部变成独立类。当前原型主要集中在ConservativeMerger。"),
        ("这里还缺的一步", "原L1提取结果没有自动携带原型依赖的user_id。测试中明确提供了这个字段，但正式接入时必须从调用方或可靠来源传递。参与者相同不代表每条事实都属于同一个人，sample_id也不一定是用户ID。"),
    ]),
    ("逐页讲解参考：第 9—11 页", [
        ("第9页：合并后的结果", "确认B覆盖A的信息后，保留B，并将来源记成[a,b]，同时记录合并成员。代表文本只是已有内容，不是重新生成的摘要。来源列表目前属于粗粒度追溯，不能证明每个来源都支持输出中的每一句话。"),
        ("第10页：这次确实验证了什么", "这一步运行了真实SemanticGraph、SemanticMap、FAISS、BM25和RocksDB。合并结果经过原写入适配和GraphWriteQueue入图，能检索到补充信息，并在关闭图资源后由新进程重新加载。还检查了冷节点删除和已保存BM25索引的加载。"),
        ("第10页需要主动说明的边界", "嵌入使用的是6维确定性测试向量，查询和内容的特征是事先设计好的。因此这个检查说明数据、索引和磁盘之间能正确传递，不说明真实语言模型的语义理解更好。来源关系边由测试显式添加，并不是当前合并组件已经自动生成。"),
        ("第11页：目前完成与未完成", "已经完成源码梳理、独立原型和真实存储检索链路检查。还需要补主体信息传递，处理条件和时间差异，并接入完整构建流程。完整三塔检索、L2生成和最终问答质量仍没有验证。"),
        ("可以用来结束汇报的一段话", "目前的判断是，这个改进有明确的接入点，存储和恢复链路也能支持合并后的数据。但现在还不能说方案已经有效，接下来主要补可靠的判定和完整流程，再用复核过的数据看效果。"),
    ]),
    ("可能被问到的问题", [
        ("1. 这是不是重新开发一个记忆系统？", "不是，主要在原L1去重位置增加判断和来源维护，复用原有图、索引和保存恢复接口。"),
        ("2. 为什么不直接让模型重新总结？", "重新总结可能压缩更多，但也更难判断有没有漏掉事实或生成错误。第一版先选已有文本，控制范围；受约束摘要可以以后再考虑。"),
        ("3. 为什么相似度高还不能合并？", "相似度用于找候选。‘喜欢辣’与‘不喜欢辣’在文本上很接近，事实却不同；条件、数字和时间也有类似问题。"),
        ("4. 原系统不是已经有去重和摘要了吗？", "有。本次重点是检查原有合并后处理，考虑更完整的代表选择、来源汇总和异常保护，而不是宣称首次增加去重。"),
        ("5. 为什么不直接删已有图中的节点？", "那会涉及关系迁移、索引更新和来源引用，范围更大。目前先在新L1写入之前处理；已有历史图的合并仍待验证。"),
        ("6. 测试通过是否说明整个功能完成？", "不能。图、索引和保存恢复通过的是受控向量下的连接检查，语义判定、主体信息和完整构建仍有待完成。"),
        ("7. 是否已经证明节省内存或提高问答质量？", "没有。减少摘要条数不等于同等比例减少总存储；L0、向量和来源元数据还可能保留。需要另外测量。"),
        ("8. 第一次阶段汇报最重要的成果是什么？", "讲清原系统怎样工作、具体改哪里、为什么这样设计，以及验证到了哪里。不能把计划、原型和完整实现混在一起。"),
    ]),
    ("源码与验证记录速查", [
        ("阅读顺序", "先读core/memory_unit.py、memory_space.py，理解内容和归属；再读semantic_map.py和semantic_graph.py，理解索引和关系。之后沿auto_builder/high_level_memory.py进入分层构建流程。以上路径都相对于Mandol的src/mandol目录。"),
        ("与本题最直接相关的入口", "auto_builder/hierarchical_builder.py：L1ExtractionResult、deduplicate_l1()、add_to_semantic_system()；auto_builder/high_level_memory.py：_build_hierarchical()；auto_builder/graph_write_queue.py：GraphWriteQueue。"),
        ("检索与恢复入口", "core/semantic_graph.py：save_graph()、load_graph()；core/semantic_map.py：search_similarity_by_text()；retrieval/bm25_retriever.py：search()、save_index()、load_index()；storage/tiered_storage_manager.py负责换出协调。"),
        ("已经留存的验证材料", "verify_graph_storage.py是真实组件验证；test_feasibility.py是早期连接检查。results/graph_storage/verification.json记录版本、源码哈希和快照路径，run.log及fresh-process日志保留执行过程。另运行上游tests/test_rocksdb_tiered_cache.py，19项通过；这些上游测试也使用模型替身。"),
        ("复查时注意", "需要Python 3.12、固定上游源码，以及requirements-graph-test.txt中的依赖。按图存储与恢复验证.md准备tmp目录后运行python verify_graph_storage.py。不需要API密钥。该测试依赖较完整，不要与只使用标准库的早期实验混淆。"),
        ("参考来源与版本记录", "课程大作业说明第1—3页；官方仓库https://github.com/AgentCombo/Mandol；本次源码提交6d7af4f004e1b311fb5c93d3e14fab90677942d8。版本只用于复查，不恢复到演示封面。完整实现、独立人工标注和语义效果评测仍未完成。"),
    ]),
]

body=ParagraphStyle('body',fontName='RefBody',fontSize=11,leading=17,textColor=colors.HexColor('#20394B'),wordWrap='CJK')
head=ParagraphStyle('head',parent=body,fontName='RefHead',fontSize=12.5,leading=20,spaceBefore=10,spaceAfter=5)
title=ParagraphStyle('title',parent=head,fontSize=19,leading=27,spaceBefore=0,spaceAfter=13)
story=[]
md=['# Mandol 近重复记忆合并改进：汇报参考资料','', '配套11页演示稿。供汇报准备与问题查阅，非结题报告。','']
for i,(name,sections) in enumerate(PAGES):
    if i:story.append(PageBreak())
    story.append(Paragraph(escape(name),title))
    md += ['## '+name,'']
    for label,content in sections:
        story.extend([Paragraph(escape(label),head),Paragraph(escape(content),body)])
        md += ['### '+label,'',content,'']

def footer(canvas,doc):
    canvas.setStrokeColor(colors.HexColor('#D8E2E8'))
    canvas.line(44,42,551,42)
    canvas.setFillColor(colors.HexColor('#536A77'))
    canvas.setFont('RefBody',9)
    canvas.drawString(44,28,'Mandol 大作业 / 汇报参考资料')
    canvas.drawRightString(551,28,str(doc.page))

pdf=OUT/'Mandol近重复记忆合并_汇报参考资料.pdf'
SimpleDocTemplate(str(pdf),pagesize=(595.276,841.89),leftMargin=44,rightMargin=44,
                  topMargin=43,bottomMargin=59,title='Mandol汇报参考资料',author='课程大作业').build(story,onFirstPage=footer,onLaterPages=footer)
(ROOT/'汇报参考资料.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
print(pdf)
