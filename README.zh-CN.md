# book2skill

[English](README.md) · [MIT 许可证](LICENSE) · [下载 v0.0.4](https://github.com/sufferfml/book2skill/releases/tag/v0.0.4)

把全书中分散的前提、论证、方法与边界重建为可追溯的框架，再生成用于新问题的 skill。多书先分别提炼与核查，再通过独立流程判断哪些框架值得整合，哪些应保留为条件性替代或保持分离。

**当前为 0.0.4 实验版本：工程流程可运行，尚未通过正式留出案例评估证明迁移效果。** 宿主 Agent 负责阅读、理解和评审；Python 工具负责提取、证据定位、持久记录、恢复、校验及评估组织，不会自行调用模型。

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
