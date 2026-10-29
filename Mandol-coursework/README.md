# Mandol 大作业：近重复记忆合并改进

这是面向对象程序设计大作业的阶段记录，选择的是 Mandol 智能体记忆系统中的“超长记忆增强”方向。

**目前还没有全部完成。** 现在主要完成了源码阅读、问题分析、初步设计和一些组件级实验，还没有把改进功能完整接入 Mandol，也没有验证整个系统的最终效果。这里的材料用于第 8、9 周的初步汇报，不是结题成果。

## 先看哪些材料

- [演示汇报 PDF](report/Mandol近重复记忆合并_演示汇报.pdf)：11 页横向演示稿，介绍系统结构、初步方案和存储链路验证，不放入小规模语义实验分数。
- [逐页讲稿 PDF](report/Mandol近重复记忆合并_汇报讲稿.pdf)：与11页演示稿一一对应，按口语写成，可直接参考讲解；另有[可编辑讲稿](汇报讲稿.md)。原参考资料链接也已更新为讲稿。
- [阶段报告](阶段报告.md)：较完整的过程记录，其中第 8 节保留了补做的实验及局限。
- [课堂分享提纲](课堂分享提纲.md)：准备课堂分享时参考的提纲。
- [图存储与恢复验证](图存储与恢复验证.md)：真实图、FAISS/BM25检索及RocksDB保存恢复的检查范围与结果。

## 为什么考虑这个问题

长期对话中，同一件事经常出现好几次。有的只是换了说法，有的却增加了返回日期、例外条件等信息。我的想法是在原来的 L1 去重流程中增加检查：能确认重复时再合并，同时汇总来源；不能确认时先保留。

第一版先考虑普通文本摘要，尽量选择信息更全的已有内容，暂时不让模型重新生成摘要。不同主体，以及否定、数字、时间、条件上的差异，都需要单独考虑。

## 目前的进度

| 内容 | 当前情况 |
|---|---|
| 理解模块、核心对象和写入、构建、检索流程 | 已完成第一轮阅读 |
| 定位原来的 L1 去重实现 | 已定位到 deduplicate_l1() |
| 合并对象与流程设计 | 已形成初步方案，接口还会调整 |
| 保守合并原型 | 已有独立原型，规则比较简单 |
| 小规模实验 | 已做受控、离线及真实模型组件实验，不能代替系统验证 |
| 接入 Mandol 原流程 | 未完成 |
| 条件范围、语义近似等判断 | 仍有问题，需要改进 |
| 图、FAISS/BM25及保存恢复一致性 | 已通过小型真实组件检查，嵌入使用确定性测试向量 |
| 人工复核标注、L2 与真实语义检索效果 | 未完成 |

## 文件说明

| 文件或目录 | 内容 |
|---|---|
| report/ | 演示 PDF |
| 阶段报告.md、课堂分享提纲.md | 书面记录与分享思路 |
| mandol-baseline.json | 原项目版本记录 |
| build_slide_pdf.py | 演示 PDF 生成脚本 |
| requirements-report.txt | 生成 PDF 的依赖 |
| experiment.py | 固定返回值检查和保守合并原型 |
| small_study.py | 开发集、评测集分开的离线比较 |
| collect_model.py | 采集真实模型返回 |
| real_model_study.py | 严格口径的返回回放 |
| replay_all_responses.py | 全部返回的补充分析 |
| test_study.py | 评测逻辑检查 |
| data/、results/ | 样例、初始标注、实验方案和已保存结果 |

## 准备源码和运行环境

实验脚本使用 Python 3.12 和标准库，不需要先安装 Mandol 的完整模型依赖，但会读取固定版本源码。请在课程仓库根目录准备两个相邻目录：Mandol/ 放上游源码，Mandol-coursework/ 放本次作业。

在仓库根目录执行：

```powershell
git clone https://github.com/AgentCombo/Mandol.git Mandol
git -C Mandol checkout 6d7af4f004e1b311fb5c93d3e14fab90677942d8
cd Mandol-coursework
```

完整版本记录见 [mandol-baseline.json](mandol-baseline.json)。上游源码单独下载，不随本次作业重复提交。封面不展示版本号，但实验仍需要固定源码以方便复查。

## 重算已有实验

以下命令不调用模型，也不需要密钥：

```powershell
python experiment.py
python small_study.py
python real_model_study.py
python replay_all_responses.py
python -m unittest test_study -v
```

实验分三部分：

1. experiment.py 的 15 组固定返回值样例，只检查后处理逻辑。
2. small_study.py 使用 48 组合成样例，其中 16 组开发、32 组评测。候选由规则产生，正反输入顺序各检查一次。
3. 真实模型部分保留了 qwen3.6-flash 的 64 次返回。严格格式统计和全部返回补充回放分开保存，没有把格式偏差的回答悄悄删掉。

主要结果见 [离线比较](results/pilot/评测结果.md)、[严格口径结果](results/real_model/真实模型评测结果.md)和[全部返回补充回放](results/real_model/全部返回补充回放.md)。

数据和初始标注由 AI 编写，尚未经过独立人工复核。原型仍会误合并部分条件句。来源 ID 保留、文本字符减少也不等于语义完全正确或实际节省了相同比例的内存。

## 检查图存储与保存恢复

图与存储检查单独运行，不需要密钥，但需要安装较完整的依赖：

```powershell
python -m pip install -r requirements-graph-test.txt
python verify_graph_storage.py
```

请先按[验证说明](图存储与恢复验证.md)准备tmp目录。此检查使用真实图和索引，不评价语义模型质量。

## 如需重新调用模型

在本机环境变量中配置 DASHSCOPE_API_KEY，不要把密钥写进脚本或提交到仓库。可通过 DASHSCOPE_BASE_URL 配置兼容接口地址，然后执行：

```powershell
python collect_model.py --model qwen3.6-flash --output results/real_model_new
```

这会产生实际接口调用。脚本拒绝覆盖已有目录；评估入口目前还固定在 results/real_model，新数据需要先调整输入目录，再单独运行评估，不能直接覆盖已有记录。这个地方后续也需要完善。

## 重新生成演示 PDF

生成脚本使用 ReportLab，默认读取 Windows 的黑体和宋体。在当前目录执行：

```powershell
python -m pip install -r requirements-report.txt
python build_slide_pdf.py
python build_speech_pdf.py
```

结果写入 report/。如果在其他系统运行，需要先将脚本中的字体路径改成本机可用的中文字体。

## 接下来准备做什么

先完善条件、时间等判断，把合并组件接入原 L1 去重位置；再使用复核过的新样例比较误合并、信息和来源保留、处理成本，并检查 L2、检索与保存恢复。当前不把这些待做内容写成已经完成。
