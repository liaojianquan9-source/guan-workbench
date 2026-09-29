# 复刻与渲染：边界、决策和验证

2026-09-21。所有旧案例、用户媒体、原工作台均保持原样。

## 依据与选择

仓库有真正的可编辑 Remotion 源码、替换样片和口播转录，但现有 `passed` 不能直接当作资产发布许可。按最新复刻校验器检查：

| 案例 | 核查结果 | 产品用途 |
|---|---|---|
| `workspace/cases/kimi-k3-000-011-test` | 普通合同校验通过；42 元素、26 动效；自动保真 needs_review | 提取月球标题、数字页，重新验证技术复用 |
| `cases/my-broll-case-motion` | 普通合同校验通过；73 元素、55 动效；自动保真 needs_review | 提取问题背景页，验证文字与图片替换 |
| `cases/kimi-k3-000-011-v2`、`cases/kimi-k3-000-071` | 旧状态 passed，但生产层直接播放 reference.mp4 | 不发布为独立可替换样式 |
| `cases/kimi-k3-000-011-authored` | 最新校验器拒绝文字截图等 7 项 | 不发布 |
| `cases/kimi-k3-097-tail` | 连续曲线校验失败 | 不发布 |
| `workspace/cases/kimi-k3-full-000-349633` | layout 仍在进行，替换证据大量缺失 | 保留未完成状态 |

保真复刻与新项目可用性回答不同问题。因此保留 `fidelity_status=needs_review`，另外用新渲染、参数替换、解码与媒体检查得到 `technical_status=passed`；符合后才有 `status=usable`。没有修改旧 QA 门或掩盖字体、时变人物排除等限制。

对照了三种集成方式：仅复用旧 MP4 不能改字换图；允许资产携带任意执行脚本会令入库本身产生代码执行；审核过的执行器注册表配不可变源码包既能真实重渲染又有确定边界，因此采用最后一种。源代码副本、素材、全部 SHA-256 位于 `renderer/SOURCE-MANIFEST.json`。共享资产中的 ZIP 包包含源码、素材、规格、依赖锁和来源清单；另一个产品可经独立资产 API 获取，执行时仍应审查包。

## 入口与实际字段

`Renderer(asset_client, work_root)` 提供合同中的 `render()`、`compose()`；`ReplicaService` 提供 `available_cases()`、`import_case()`、`study()`。

| renderer_id | 原案例帧范围，含首尾 | 参数 |
|---|---|---|
| kimi-moon-v1 | 172–299，128 帧 | title / subtitle / texture_text / image |
| kimi-number-v1 | 99–171，73 帧 | number / unit / label / annotation |
| problem-photo-v1 | 4–79，76 帧 | kicker / title / subtitle / image |

原画幅 1280×720，30 fps。原始组件保留原时间轴，先按精确范围渲染，再按草稿长度调整时间；每次报告保留原范围和实际参数。图片必须引用 `{asset_id, revision}`；新资产版本不会静默改变已批准项目。源文件、源视频和任意 URL 均不能从参数里注入。文本长度上限是保守准入范围；新内容仍需要用户审看，不能由通过参数验证推断布局完美。

每次渲染独立目录含 props.json、实际执行命令与输出、native.mp4、preview.mp4、poster.jpg、report.json。`--muted` 强制去除无用音轨；审计发现旧 replacement-demo 文档声称无声，但 MP4 实有 AAC，故新产品根据 ffprobe 结果验收，不信任文字声明。时长按 30 fps 量化，过长文本、未知字段、图片无固定版本、失败进程、音轨不符、帧数不符均失败。

导入案例在全新工作目录依次渲染原内容、异长文字/不同图片，再检查替换是否产生真实画面差异。差异数值只拒绝 no-op，不声称验证语义、布局或参考保真。导入保存独立参考源、复刻项目、样式包、原/替换视频、海报、技术报告，并建立来源关系。实际制作的每张草稿继续单独渲染与审看。

任意新视频的 study 只保存源哈希、精确范围、真实起中末抽帧、笔记，同时建立 `needs_work` 复刻任务；没有内置执行器的画面不会伪装成已复刻。下一步是运行现有 `ljq-broll-replica` 阶段流程并审核可编辑实现，再增加审查过的适配器。

最终 compose 只接受应用传入的批准快照，拒绝重叠、越界和与当前时长不符的预览。保持口播尺寸、fps、总时长；B-roll 保留全部画面比例并居中补边；音频包从原口播直接复制。所有输出全片解码。

## 验证入口

```sh
python3 -m unittest discover -s apps/broll-agent/tests -p test_rendering.py -v
```

包含真实 FFmpeg 合成、音频包字节一致性、时长/帧数/尺寸、重叠与旧预览拒绝、真实 study 抽帧、固定历史图片版本、字段验证、复制源码哈希检查。真实 Remotion 导入不是测试桩：产品案例导入会实际运行每个原版与替换版，技术报告随资产保存。

依赖优先复用本机已有锁定环境，`renderer/node_modules` 为不提交的符号链接；缺失时在 renderer 目录执行 `npm ci`。Node.js、FFmpeg、ffprobe 和 Chrome 需要可用；`BROLL_CHROME_PATH` 可指定 Chrome。没有运行外部下载脚本。

真实验证用口播是用户已有 `260907.mov`；115 条精确字幕保存在 `outputs/talking-head-260907/full-edit/alignment/alignment.json`，165.10–173.60 秒明确讲述换文案、换背景、复用原构图与运动。原 MOV 280.433 秒，讲话剪辑到约 218.033 秒，不能把已有字幕误认为覆盖了原视频后段黑屏。替换本人照片来自既有 150 秒抽帧；沿用已生成宽幅补边素材。

## 官方资料与许可边界

- [Remotion CLI render](https://www.remotion.dev/docs/cli/render) 与 [passing props](https://www.remotion.dev/docs/passing-props)：2026-09-21 核查 JSON props 文件、帧范围、静音、浏览器路径与独立输出支持。本实现使用实际安装的 4.0.518，未仅按最新网页猜测 API。
- 现有发布包原创源码 MIT。月球素材来源与署名在复制的 `kimi/remotion/public/moon/SOURCES.md`，原参考视频不随 MIT 重新授权。
- 问题页来源与字体说明在原 case 证据及复制的 `problem/remotion/public/assets/fonts/README.md`。字体子集对新汉字可能回退，因此技术通过不声明字形完全一致。

初版尚不自动生成任意参考片的布局和动效代码，也不让简单通用模板冒充完成复刻。内置范围以外的研究任务会明确等待可编辑工程，已有 Skills 的人工视觉门保持可见。

## 第二轮：固定版本、字体与失败恢复

进一步审查发现，固定资产 revision 并不自动固定运行代码；仅凭 `renderer_id` 读取当前目录会让旧版本随代码变动。因此渲染现在必须匹配已审查的 `source_manifest_sha256`，并核验清单里每个源码/素材的真实哈希、依赖文件与实际安装版本。拒绝缺失、改写、额外代码、未知清单、ZIP 越界和符号链接。优先从共享库固定 ZIP 恢复新的执行快照，再运行该快照；只有首次发布前才可从已核查的本地副本建立快照。删除仓库案例副本后，已有共享包仍可恢复。若将来更换审查清单，应显式增加新执行器/样式版本；旧版本不能静默套用新代码。新发布样式还记录参数适配合同签名。

字体也不能从“文件存在”推断实际字形。每次渲染先用同一 Chrome 实例能力检查实际字段，通过 `CSS.getPlatformFontsForNode` 保存实际 family、PostScript 名、glyphCount 和是否自定义字体，结果写入 `fonts.json` 与 `report.fonts`。加载失败或 LastResort 缺字拒绝渲染；合法回退会明确提示必须视觉审看。

| 场景 | 请求字体 | 当前机器实际核验 |
|---|---|---|
| 问题标题“解决问题” | 内置 BrollDisplay 子集 | 4 字均为 YouSheBiaoTiHei，无回退 |
| 问题标题“复刻镜头” | 同一子集 | 4 字均回退 PingFang SC，记录字形差异 |
| 问题页引导语 | BrollSubtitle / STHeitiSC-Light | Heiti SC |
| 问题页辅助英文 | BrollTech / Monaco | Monaco |
| 月球与数字页 | Helvetica Neue、Songti SC、Impact | 每次按新文字检查；中文进入拉丁字体时记录实际回退 |

这些是当前 macOS 字体条件；跨机器必须重新核验，不能宣称相同源码必然生成相同字形。没有将系统字体重新分发，也没有静默替换样式的字体参数。

真实 Agent 曾给月球副标题框输入“才能用好AI”，虽然通过 8 字符字段上限，但实际 163×119 的固定字面框把文字明显压窄。现在增加 `report.layout`：副标题中文/混合超过 4 字符、纯 ASCII 超过 5 字符，主标题中文/混合超过 4、ASCII 超过 9，会返回 `status=needs_revision` 与具体字段/框大小/建议长度。技术媒体检查仍可 passed；制作 Agent 必须修改并重新渲染。“用好AI”通过这条保守门，但仍需最终审看。此修复只增加检查，没有修改旧样式、文字或组件。

导入在包、原版、替换版、发布各阶段保存进度。视频、海报和报告进入内容寻址库，恢复时重新校验哈希；一条样式已发布、另一条失败时，只重跑失败的阶段，已完成样式不重复创建 revision。失败状态、责任阶段、诊断证据 blob 与历次失败记录保留在复刻项目中。导入重试串行，进程内渲染也串行，避免并发请求同时启动大量 Chrome。

所有渲染子进程建立独立进程组。超时先 SIGTERM，再向整组 SIGKILL；即使父进程已退出而子进程忽略 SIGTERM，也不会留后台渲染。超时日志包含执行参数、stdout/stderr 和超时标记。

第二轮 14 项测试覆盖了不可变包独立恢复、源码改写/额外文件/越界包拒绝、快照不受后续工作区改动影响、真实 Chrome 子集回退、忽略 SIGTERM 子进程清理、失败导入的阶段恢复与无重复版本，以及此前的真实合成与媒体检查。
