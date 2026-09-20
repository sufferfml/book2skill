# book2skill

[English](README.md) · [MIT 许可证](LICENSE) · [下载 v0.0.4](https://github.com/sufferfml/book2skill/releases/tag/v0.0.4)

把全书中分散的前提、论证、方法与边界重建为可追溯的框架，再生成用于新问题的 skill。多书先分别提炼与核查，再通过独立流程判断哪些框架值得整合，哪些应保留为条件性替代或保持分离。

## 与 book-to-skill 的区别

[book-to-skill](https://github.com/virgiliojr94/book-to-skill) 和 book2skill 都将书籍或文档中的知识转化为可复用的 Agent skill，都包含框架、决策规则与按需加载。两者的侧重点分别是组织可查询、可学习的知识材料，以及围绕具体任务重建、核查和整合框架。

| 维度 | book-to-skill | book2skill |
| --- | --- | --- |
| 输入与提取 | 支持 PDF、EPUB、DOCX、HTML、RTF、文本等多种格式，以及文件夹、glob 和多文件输入；可按内容选择 Docling 等提取器 | 支持 EPUB、带文本层 PDF、Markdown/TXT；保留 spine、文件页、位置和提取缺失记录，PDF 解析器随包提供 |
| 内容组织 | 以章节或主题文件组织知识，配合核心思维模型、术语表、方法库和决策速查；学习深度可加入实例、机制与失效说明 | 围绕目标任务组织主张、关系和框架，记录前提、反例与适用边界，再编译为共同核心及决策模块 |
| 来源与核查 | 通过章节引用和跨章节关联帮助定位内容，生成文字强调综合提炼 | 通过来源位置、哈希及逐项证据记录追溯主张和关系，区分作者陈述、重建和模型扩展，设置独立核查步骤 |
| 多源与更新 | 支持将多个来源生成统一 skill，也可通过 Update / Fold-in 更新章节、方法和索引 | 先分别提炼并核查每本书，再比较前提、机制与边界；保留冲突、条件切换和不融合的结果，冻结旧版作为基线 |
| 使用时读取 | 根据章节或主题索引按需读取相关文件 | 根据任务路由读取共同核心和必要模块；解释与原文核对按 ID 单独查询，完整研究档案独立保存 |
| 工作流与维护 | 提供从文档转换到安装的流程，以及仅分析、从分析生成和增量更新模式 | 提供任务提交、检查点恢复、版本失效、核查记录及对照评估协议；需要维护相应的运行和审查材料 |

如果主要希望把书籍、技术文档或多种格式资料整理成日常学习和查询入口，可以从 book-to-skill 开始；如果更关心某项任务背后的跨章节推理、结论出处，以及多本书的方法在什么条件下可以结合，可以考虑 book2skill。两种组织方式也可以服务同一批资料的不同用途。这里比较的是实现方式和使用取向，不据此判断哪一个生成的答案更好。

对比依据：book2skill 0.0.4，以及 2026-09-21 核对的 book-to-skill 提交 [`526f362`](https://github.com/virgiliojr94/book-to-skill/commit/526f362552562d88c1a8bbf8012d2cee93f831d5)。对方的 [生成规范](https://github.com/virgiliojr94/book-to-skill/blob/526f362552562d88c1a8bbf8012d2cee93f831d5/SKILL.md)、[使用方式](https://github.com/virgiliojr94/book-to-skill/blob/526f362552562d88c1a8bbf8012d2cee93f831d5/docs/usage.md) 和 [处理流程](https://github.com/virgiliojr94/book-to-skill/blob/526f362552562d88c1a8bbf8012d2cee93f831d5/docs/how-it-works.md) 提供了上述能力的具体说明；后续版本可能变化。

## 安装

环境：Python 3.11+、macOS/Linux，以及支持本地 skill 的宿主。独立发行包已内置 pypdf 6.10.0，本地命令无需另装依赖或配置 API key。模型使用和费用由宿主提供。当前使用 POSIX 文件锁，不支持 Windows。

从上方 Release 下载 `book2skill-0.0.4.zip` 和 `SHA256SUMS`，对照其中对应的校验值验证 ZIP 后解压。将完整 `book2skill/` 文件夹放入宿主的 skill 目录。例如使用 `~/.agents/skills` 的 Codex 环境：

```sh
unzip book2skill-0.0.4.zip
mkdir -p ~/.agents/skills
# 已有安装时先在发现目录之外备份；以下命令不会覆盖已有目录。
test ! -e ~/.agents/skills/book2skill && cp -R book2skill ~/.agents/skills/book2skill
python3 -S ~/.agents/skills/book2skill/scripts/book2skill.pyz --version
```

也可克隆仓库并复制 `skill/book2skill/`，或直接让宿主读取该路径的 `SKILL.md`，无需全局安装。核心指令是英文，不限制回答和生成内容使用中文。

## 如何使用

向宿主发出请求，并填入实际书籍、用途和保存目录：

> 使用 book2skill，将 `<书籍.epub / 书籍.pdf / 全文.md>` 的思考框架用于 `<具体任务>`。先判断适配性，再重建跨章节逻辑、前提与边界，核查原文依据，生成候选 skill。运行材料保存在 `<目录>`，明确尚未验证的能力。

添加另一本书：

> 独立提炼 `<新书>`，再和 `<已有 skill>` 背后的已核查框架比较。保留冲突、适用条件和旧版基线；没有增益时允许不融合。

已有安装包不等于完整的已核查输入。继续融合需要对应的提炼运行及证据，不能把几本书直接拼成一个长上下文。

流程：适配判断 → 分批阅读与覆盖登记 → 框架重建 → 独立来源核查 → 多书比较与整合核查（如适用）→ 研究包 → 应用编译与独立核查 → 按需运行包及独立审查档案 → 新问题对照评估。

完整说明见 [技能入口](skill/book2skill/SKILL.md)、[提炼流程](skill/book2skill/references/workflow.md)、[多书整合](skill/book2skill/references/fusion.md)、[应用编译](skill/book2skill/references/runtime.md) 和 [评估流程](skill/book2skill/references/evaluation.md)。

## 先用合成材料试运行

```sh
python3 -S skill/book2skill/scripts/book2skill.pyz --help
python3 -S skill/book2skill/scripts/book2skill.pyz inspect examples/synthetic-book.md
python3 -S skill/book2skill/scripts/book2skill.pyz template config --out config.json
```

填写用途、宿主/模型身份和预算后，再按提炼流程执行 `init` 及 `task → Agent 处理 → submit`。

开发与完整工程演示：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/run_demo.py runs/single-demo
python examples/run_fusion_demo.py runs/fusion-demo
python tools/build_skill.py
python tools/check_release.py
```

演示目录必须是新位置。演示使用虚构短书和人工编写的结构记录，不代表真实模型答案或独立语义评审。

## 能力与边界

- 支持 EPUB、带文本层 PDF、Markdown/TXT；不包含 OCR。保留 spine/文件页定位和提取缺失提示；图像、复杂表格、公式、多栏需要额外核查。
- 每个单书或整合模型包含 1–3 个核心框架；多书数量没有固定两本上限，但成对比较、快照和最小核查上下文限制实际规模。
- 持久化、分页与预算有助于管理上下文，不保证无限书长，也不证明理解。完整必要单元超限会停止，不会静默删除边界。
- 核查者身份与上下文隔离依赖宿主；工程校验不认证评审者独立性，也不证明框架正确或应用有效。
- 没有内置 Jev、向量数据库或外部模型 API；未知 token 与金额保持未知，字符读取量不能当作费用数据。
- 默认研究包与带证据运行包可能包含书籍原文。`compile-package --evidence locators` 不附摘录，此时原文核对会明确不可用；不会自动关联用户电子书，也不等于获得内容分发授权。

仓库只公开生成器、合成示例、测试和通用文档，不包含商业书、私有研究运行或业务应用 skill。项目原创代码与文档采用 MIT；第三方依赖及输入书籍适用各自权利边界，见 [声明](THIRD_PARTY_NOTICES.md)。
