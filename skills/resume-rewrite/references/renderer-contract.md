# PDF 渲染脚本约定

脚本只排版已经写好的简历，不补写信息，不核实经历，也不替代整页视觉检查

## 调用

从仓库根目录运行：

```sh
python skills/resume-rewrite/scripts/render_resume_pdf.py \
  --markdown examples/fictional-resume.md \
  --output output/resume.pdf \
  --style plain \
  --font /path/to/licensed-static-font.ttf
```

安装 ZIP 或复制 Skill 后，进入安装后的 `resume-rewrite` 文件夹运行：

```sh
python -m pip install -r requirements.txt
python scripts/render_resume_pdf.py \
  --markdown /path/to/confirmed-resume.md \
  --output /path/to/output/resume.pdf \
  --style plain \
  --font /path/to/licensed-static-font.ttf
```

安装包只含 Skill 本身；示例、预览和开发测试位于源码仓库。

依赖：`reportlab`、`Pillow`、`pypdf`；Python 3.10 或更新版本

| 参数 | 含义 |
| --- | --- |
| `--markdown` | 必填，UTF-8 Markdown 输入；允许 UTF-8 BOM |
| `--output` | 必填，独立的 `.pdf` 输出路径 |
| `--style plain` | 默认，无照片，左对齐单列，便于提取文本；不保证所有 ATS 的解析结果 |
| `--style classic` | 灰色矢量弧顶、居中姓名，可选圆形头像 |
| `--font` | 具有所需字形且允许使用的静态 TrueType TTF/TTC |
| `--font-index` | TTC 子字体索引，默认 0；只在指定 `--font` 时使用 |
| `--photo` | 候选人提供的原照片，仅 `classic` 接受；省略时不画占位头像 |
| `--photo-shift-up-pt` | 在固定圆框内上移图像，默认 0；超过安全裁切范围时失败 |
| `--qa` | 独立的 `.json` 检查记录，默认 PDF 同名 `.layout.json` |
| `--no-qa` | 不写检查记录；不能与 `--qa` 同时使用 |

无照片的 `classic` 会缩短页头。`plain` 搭配 `--photo` 明确报错，不悄悄丢掉照片

## 输入格式

```markdown
# 示例候选人（虚构）

求职意向：目标岗位｜城市：示例城市
邮箱：candidate@example.com

## 个人总结

已确认的总结文字。原有句号会保留

- 第一条已确认能力
  这是同一条的缩进续行
- 第二条已确认能力

## 工作经历

**示例公司｜示例岗位｜2022.07 - 2025.08**

已有的职责与结果，不要求必须使用列表

**另一家示例公司｜另一岗位**
2020.07 - 2022.06

1. 已确认的第一项工作
2. 已确认的第二项工作

## 教育经历

示例学校｜示例专业｜本科

## 自定义章节

自定义标题和段落会保留
```

- 首个非空行必须为 `# 姓名`，至少提供一个 `## 章节`；不生成示例姓名或缺失章节
- 页头每项必须明确标注字段，不推断无标签的文字是城市、电话或学校
- 中文字段支持：求职意向、目标岗位、电话、手机、联系方式、微信、邮箱、电子邮箱、毕业院校、学校、院校、城市、所在地、求职城市、网站、作品集、领英
- 英文字段支持：Target、Role、Phone、Contact、Email、City、Location、School、Website、Portfolio、LinkedIn，大小写均可
- `｜` 或 `|` 分隔页头字段；每项原标签与内容都会显示，不把微信改成电话，不把学校自动搬到教育经历
- `工作经历`、`实习经历`、`Work Experience`、`Experience`、`Employment` 按公司条目解析；其他标题按普通章节保留
- 工作条目使用 `公司｜岗位` 或 `公司｜岗位｜时间`。日期可另起一行，缺失时省略
- 日期支持 `YYYY`、`YYYY.MM`、`YYYY-MM`、`YYYY/MM`、`YYYY年M月` 的范围；结束可为 `至今`、`现在`、`Present` 或 `Current`
- 普通段落、`-`/`*`/`+` 列表、`1.`/`1)` 有序列表均可；数字标号按输入显示
- `**粗体**` 是支持的行内格式。其他普通字符如 `&`、`<`、`>` 保留；不支持 Markdown 链接、表格或 HTML 排版，它们不会转为可点击链接或表格
- 两个空格或制表符开头的续行接到前段，空行断开续行；普通非空行各自成为一个段落
- 完整 HTML 注释不进入 PDF。未闭合注释、未配对粗体、嵌套标题、引用说明和代码块会报错，不能把待确认备注藏进正文
- 原标点、日期、数字和重复段落均保留，不自动删句号、改写文字或补写缺失事实

## 字体与资源

建议始终用 `--font` 指定字体，并确认字体许可允许当前使用及 PDF 嵌入

未指定时先读 `RESUME_FONT` 环境变量，随后仅在技能的 `assets/fonts` 和常见系统字体目录查找 Noto Sans SC、Noto Sans 或 DejaVu Sans 的固定文件名。不会扫描个人文档，也不会下载字体。`RESUME_FONT` 指定的字体不可用时直接报错，避免悄悄替换用户选择

脚本先检查全文每个非空白字符是否有字形。任一缺字都会停止并显示部分缺字字符及 Unicode 编码，不能用方块字交付。字体需要 TrueType 轮廓；变量字体或 CFF 字体应先在本地准备兼容的静态 TTF，再传入脚本

公开包不含商业系统字体、原模板纹理、图标字体或真实照片；页头和章节标记由矢量路径绘制。测试使用依赖包安装时自带的 Vera 字体，不向仓库复制字体。测试照片临时生成，用完删除

当前排版针对中文与拉丁文字，不提供复杂文字塑形、双向文本或 RTL 版式保证。字形存在不等于复杂文字已正确塑形；这类输入应使用支持相应文字的排版工具并人工检查

## 保护与验收

1. 只生成一页 A4。先缩短段距，再调整行距和字号；正文与工作日期最低 10 pt
2. 超出一页容量时以退出码 2 停止，保留旧 PDF。不删内容、不转成多页、不继续缩成小字
3. 在输出目录生成临时 PDF，检查页数、A4 尺寸、字形以及全部文本，再通过原子替换保存
4. 文本检查比较完整阅读顺序的字符序列，仅忽略排版空白和约定的 Markdown 标记。漏掉重复段落、改动数字或额外增加文字都会失败
5. 生成前后检查源 Markdown 和原照片哈希。它们不会被修改；输入过程中发生变化则停止
6. QA JSON 先写到临时文件，然后单独原子替换；PDF 与 JSON 是两个文件，不能保证文件系统故障时作为一个事务同时提交。QA 中的 PDF SHA-256 可确认二者对应关系
7. QA 记录文件名和哈希、UTC 时间、字体文件名和哈希、字号、段落边界。它不记录用户目录或字体的绝对路径
8. `visual_review.status` 初始为 `pending`，`content_verification.status` 为 `not_performed`。程序通过不代表履历属实、页面美观或已经人工验收

最后必须把最新 PDF 渲染成整页图，检查文字、换行、边界和头像裁切。短稿不自动撑满一页；已有内容放不下时由作者精简，排版脚本不替作者删改

## 功能测试

以下仅在源码仓库根目录执行，安装 ZIP 不包含 `tests/`：

```sh
python -m unittest discover -s tests -v
```

覆盖缺失信息不补写、原文件不变、自然段与列表、重复文本与特殊字符、自定义章节、可选照片、缺字失败、溢出保留旧输出、全量文字比较、输入路径保护与 `--help` 无副作用
