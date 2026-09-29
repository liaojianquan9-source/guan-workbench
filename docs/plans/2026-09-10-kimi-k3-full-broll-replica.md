# KIMI K3 Full B-roll Replica Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 把 349.633 秒参考片整理成一个可恢复、可编辑、可替换、按台词节点检索的 Remotion B-roll 母案例，并输出 10,489 帧整片、独立节点镜头、证据与 QA 报告。

**Architecture:** 只维护一个 `kimi-k3-full-000-349633` 案例与一个全片时间真源。案例内部使用 `Chapter → Shot → Beat/Node → Element/Track` 四级结构；先完成全片逐词对齐、镜头边界和节点账本，再搭建 10,489 帧骨架，最后按五个连续章节迁移或重建镜头。旧案例只读复用，不原位修改；场景通过 registry 接入 master composition，避免巨型单文件。

**Tech Stack:** FFmpeg/ffprobe、faster-whisper small（本地离线）、JSON/JSON Schema、React 19、TypeScript 5.9、Remotion 4.0.518、现有 `ljq-broll-replica` / layout / motion / QA 工具链。

---

## 已锁定的输入与边界

- 参考画面：`/Users/liaojianquan/Documents/03_Study/自媒体-视频/08_AI剪辑库/01_素材搜集/04-KIMI_K3：国产AI追上来了吗_视频.mp4`
- 口播音频：`/Users/liaojianquan/Documents/03_Study/自媒体-视频/08_AI剪辑库/01_素材搜集/04-KIMI_K3：国产AI追上来了吗_音频.m4a`
- 原文：`/Users/liaojianquan/Documents/03_Study/自媒体-视频/08_AI剪辑库/01_素材搜集/04-KIMI_K3：国产AI追上来了吗_原文.md`
- 母案例：`workspace/cases/kimi-k3-full-000-349633/`
- 时间真源：1280×720、30fps、帧 `0–10488`、总计 `10489` 帧；末帧结束时间为 `349.633333s`。
- 内容范围：复刻可见 B-roll、文字、数字、图形、媒体槽、材质、镜头运动与转场；不把人物 A-roll、烧录字幕和左上角标识做成模板层。
- A-roll 段在 B-roll 母时间线中登记为 `holdout`，不伪造为 B-roll；最终审阅合成可以引用参考 A-roll 作为只读底板。
- 第三方网页、照片、Logo 默认作为可替换媒体槽并记录来源状态；没有原始合法素材时，不把参考视频裁片冒充完全可编辑资产。

## 命名与数据合同

- Chapter：`C01` 至 `C05`。
- Shot：`Cxx-Sxx`，对应硬切、软切或视觉体制变化。
- Beat/Node：`Cxx-Sxx-Bxx`，对应一句或短语触发的一次视觉状态变化。
- Element：`Cxx-Sxx-E-<semantic-name>`；同一 Shot 内跨 Beat 保持稳定 ID。
- 边界：`Cxx-BND-xx`，独立记录 transition owner、前后 handles 与交叠帧。
- 所有最终时间同时保存 `startUs/endUs` 与 `startFrame/endFrameExclusive`；浮点秒只用于展示。

每个节点至少包含：台词、词级起止、视觉目的、前后状态差、受影响元素、素材引用、入场/停留/出场、可替换参数、entry/peak/hold/exit 证据帧、置信度和人工状态。

## 分章工作包

| Chapter | 原始范围 | 说明 |
| --- | --- | --- |
| C01 | 00:00.000–01:32.000 | 开场、参数、关键任务、网页能力、榜单与信任转折；优先迁移旧 0–71 秒案例 |
| C02 | 01:32.000–02:34.000 | 截图还原与五口之家旅行长链路案例；信息密度最高 |
| C03 | 02:34.000–03:38.000 | 长链路定义、42/35 分与检索能力、花架子反转 |
| C04 | 03:38.000–04:30.000 | 14 项对比、57/60、幻觉率与正确率 |
| C05 | 04:30.000–05:49.633 | 中国开源榜单、中美路线、总结与 CTA |

章节只是执行批次，不是独立案例。所有章节从第一天起都登记在同一个 master timeline；批次边界要额外渲染前后 15–30 帧 handles。

### Task 1: 冻结来源与预检合同

**Files:**
- Verify: `workspace/cases/kimi-k3-full-000-349633/case.json`
- Verify: `workspace/cases/kimi-k3-full-000-349633/evidence/source.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/source-provenance.json`

**Step 1: 校验案例状态**

Run:

```bash
node /Users/liaojianquan/.codex/skills/ljq-broll-replica/scripts/validate-case.mjs workspace/cases/kimi-k3-full-000-349633
```

Expected: `Valid case`，`preflight=passed`，10489 解码帧，音轨存在。

**Step 2: 记录三份原始输入的哈希与派生 AV 合并文件**

`source-provenance.json` 必须保存视频、音频、原文和 `workspace/inputs/kimi-k3-full-reference-av.mp4` 的绝对路径、字节数、SHA-256、时长及“音频长 20.02ms、以画面帧数为权威”的裁切决定。

**Step 3: 做不可变检查**

重新计算哈希，确认用户原始文件没有被写入；后续任何阶段都只读它们。

### Task 2: 生成逐词对齐与校正版句段

**Files:**
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/whisper-raw.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/aligned-transcript.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/aligned.srt`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/alignment-qa.json`

**Step 1: 运行本地离线 ASR**

复用已缓存的 `Systran/faster-whisper-small`，启用 `word_timestamps=true`，不下载模型、不上传音频。

**Step 2: 先保留模型原始词级结果**

`whisper-raw.json` 不做人工改字，保留每个 segment/word 的 start、end、probability。

**Step 3: 用用户原文校正文本，不改写时间证据**

按 10 个粗锚点做分区匹配；专有名词固定为 Kimi K3、K2.6、o1、Claude、GPT、Artificial Analysis、GLM-5.2、DeepSeek、MiniMax、Gemma、Meta、OpenAI。

**Step 4: 生成句/短语级区间**

长枚举、数字对比和视觉状态变化句允许拆为多个短语；每段保存匹配分数和是否需人工复核。

**Step 5: 运行对齐 QA**

Expected: 文本顺序完整、时间不倒退、无重叠、所有 endFrameExclusive ≤10489、未对齐原文字符有明确清单。

### Task 3: 生成镜头边界候选与全分辨率证据

**Files:**
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/scene-candidates.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/scene-contact-sheet.jpg`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/boundary-review.md`

**Step 1: 运行三档视觉变化检测**

保留强切阈值、软切阈值和低阈值候选，不把阈值结果直接当最终节点。

**Step 2: 为每个候选边界提取前后帧**

每处至少检查 `-2/-1/0/+1/+2` 帧；溶解或推拉转场增加 15–30 帧窗口。

**Step 3: 人工归类**

每个 Shot 标为 `broll`、`aroll-holdout`、`mixed-transition` 或 `uncertain`，并说明边界置信度。

**Step 4: 覆盖旧案例范围**

对 0–71 秒与 98.000–106.733 秒，比较当前源片与旧证据；只在帧对应成立时迁移组件。

### Task 4: 建立台词到 B-roll 的节点账本

**Files:**
- Create: `workspace/cases/kimi-k3-full-000-349633/specs/beats.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/specs/nodes.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/NODEBOOK.md`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/validate-node-ledger.mjs`

**Step 1: 写失败的覆盖测试**

测试要求每个对齐语义段都必须有 `yes/maybe/no` 或 `aroll-holdout` 结论；节点帧范围不能越界。

**Step 2: 运行测试并确认当前失败**

Expected: 因 `beats.json` / `nodes.json` 尚未完成而 FAIL。

**Step 3: 合并语义段与视觉变化**

以台词为主、视觉 cut 为证据：同一句内连续出现三个数字卡片时可建 3 个 Beat；同一镜头只是元素更新时不新建 Shot。

**Step 4: 为每个节点写因果关系**

记录“说了什么 → 为什么需要这个画面 → 画面具体变化 → 哪些元素可换”，禁止只写“这里放 B-roll”。

**Step 5: 运行账本校验**

Expected: 所有对齐段有结论；所有 B-roll Shot 至少由一个 Beat 引用；无孤儿元素、空 ID、倒置时间或越界帧。

### Task 5: 建立整片 Remotion 骨架

**Files:**
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/composition.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/runtime.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/schema.ts`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/scene-registry.ts`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-01.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-02.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-03.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-04.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-05.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/planning/validate-timeline-coverage.mjs`

**Step 1: 写失败的 10489 帧覆盖测试**

要求 master timeline 从帧 0 连续覆盖到 10489，所有片段使用 `[startFrame,endFrameExclusive)`，不允许 gap/overlap。

**Step 2: 只接入占位 registry**

每个 Shot 先使用稳定 ID 和颜色/标签占位；A-roll 段为透明或 holdout，不复制成独立组件。

**Step 3: 接入独立口播音频**

音频起点为 0；合成总帧仍固定 10489，尾部 AAC padding 不延长 composition。

**Step 4: 渲染低成本全片骨架**

Expected: 1280×720、30fps、10489 帧，音频可解码，所有节点按时间出现，无黑洞式漏段。

### Task 6: 迁移并回归旧 0–71 秒场景

**Files:**
- Read only: `cases/kimi-k3-000-071/`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/scenes/opening/`
- Create: `workspace/cases/kimi-k3-full-000-349633/assets/reused/opening/`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/migrations/opening.json`

**Step 1: 比较当前源片与旧源片的关键边界**

Expected: 0–71 秒帧时序可映射；不只依赖整段 SSIM。

**Step 2: 复制组件到新命名空间并去掉原字幕/角标层**

旧 passed 案例保持不变；新组件使用 master 的稳定 element IDs。

**Step 3: 逐场景静帧回归**

对每个迁移场景生成 source/render/comparison still；媒体槽做至少一次替换 still。

**Step 4: 渲染 C01 范围与边界 handles**

Expected: 已迁移区的主要构图和动效保持，A-roll holdout 与 B-roll 之间无闪帧。

### Task 7: 校正并迁移 98.000–106.733 秒旧案例

**Files:**
- Read only: `cases/kimi-k3-097-tail/`
- Create: `workspace/cases/kimi-k3-full-000-349633/remotion/scenes/png-to-html/`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/migrations/png-to-html.json`

**Step 1: 先重现当前连续性校验失败**

Expected: 旧 `motion.motions[10].transform.x` 报 nonlinear easing restart。

**Step 2: 在新案例副本中拟合连续曲线**

不得编辑旧案例；只修复迁移版本。

**Step 3: 运行动效连续性和代表帧比较**

Expected: 新副本通过当前校验，快速运动中的已知像素差异单独记录。

### Task 8: 完成三类校准场景并冻结设计系统

**Files:**
- Create: `workspace/cases/kimi-k3-full-000-349633/specs/style-system.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/calibration/`

**Step 1: 选择三个代表原型**

至少覆盖：大数字/标题图形、网页或排行榜、实拍/多素材叙事拼贴。

**Step 2: 每个原型先过静态布局门**

位置、尺寸、锚点、字体角色、层级、裁切和材质分别记录 measured/inferred。

**Step 3: 再过 motion 门**

记录 entry、settle、hold、exit、camera 与 boundary transition。

**Step 4: 冻结全片共用规则**

固定字体角色、颜色、圆角、阴影、噪声、字幕/角标排除和转场责任；后续章节只能显式覆盖。

### Task 9: 五章布局实现

**Files:**
- Modify: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-01.tsx`
- Modify: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-02.tsx`
- Modify: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-03.tsx`
- Modify: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-04.tsx`
- Modify: `workspace/cases/kimi-k3-full-000-349633/remotion/chapters/chapter-05.tsx`
- Create: `workspace/cases/kimi-k3-full-000-349633/evidence/layout/<scene>-source.png`
- Create: `workspace/cases/kimi-k3-full-000-349633/evidence/layout/<scene>-render.png`
- Create: `workspace/cases/kimi-k3-full-000-349633/evidence/layout/<scene>-comparison.png`

对 C01–C05 逐章重复：先写当前章失败的场景完整性测试；只实现布局；渲染每个场景的 settled still；逐一记录 pass/needs_review；通过后才进入下一章。C02 信息量最高，不与其他章同时修改共享样式。

### Task 10: 五章动效取证与实现

**Files:**
- Create/Modify: `workspace/cases/kimi-k3-full-000-349633/specs/motion.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/evidence/motion/`

对 C01–C05 逐章重复：提取 entry/peak/hold/exit 及边界窗口；camera 与 element 轨分开；文字内部动画独立记录；运行连续性分析；渲染带 handles 的 range preview；通过后冻结该章 motion。

### Task 11: 可替换性与来源门

**Files:**
- Create: `workspace/cases/kimi-k3-full-000-349633/specs/replacements.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/replacements/`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/provenance.json`

**Step 1: 每个 scene family 定义 props 和资产槽**

必须记录文字长度/数字位数、图片比例、裁切策略、最小尺寸和安全区。

**Step 2: 做真实替换冒烟**

每个 family 至少改一次文字/数字/图片/Logo；高风险独特场景逐个测试。

**Step 3: 标记第三方素材路线**

区分 `user-owned`、`licensed`、`reference-only`、`replacement-required`；来源不明不宣称可商用。

### Task 12: 全片渲染与 QA

**Files:**
- Create: `workspace/cases/kimi-k3-full-000-349633/render/final.mp4`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/gates.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/report.json`
- Create: `workspace/cases/kimi-k3-full-000-349633/validation/iterations/pass-1/`

**Step 1: 先跑时间线与节点覆盖测试**

Expected: 10489 帧 100% 覆盖，所有 B-roll Shot 与 Beat 双向引用，无 gap/overlap。

**Step 2: 渲染完整 MP4**

Run:

```bash
/Users/liaojianquan/.codex/skills/ljq-broll-replica/scripts/render-case.sh workspace/cases/kimi-k3-full-000-349633
```

Expected: 1280×720、30fps、10489 帧、口播音频存在且尾部不漂移。

**Step 3: 运行四级 QA**

- 节点：台词映射、视觉目的、元素 delta。
- 场景：source/render 的 entry/peak/hold/exit。
- 章节：range render、handles、黑帧/闪帧、时间误差。
- 整片：媒体规格、全片节点覆盖、边界连续性、音画终点。

**Step 4: 最多两轮定向修正**

每轮只处理一个最高影响 owner；保留旧报告，不静默覆盖。

**Step 5: 完整合同校验**

Run:

```bash
node /Users/liaojianquan/.codex/skills/ljq-broll-replica/scripts/validate-case.mjs workspace/cases/kimi-k3-full-000-349633 --complete
```

Expected: 案例、规格、源码、成片、替换证据和 QA 全部通过；否则保留真实未过项。

## 存储与恢复规则

- 不复制 `node_modules`；所有章节共用现有 renderer。
- 不保存全片逐帧 PNG；仅保留候选边界窗口、settled still、motion probes 和 QA 必需证据。
- 每次全片渲染前先跑单章范围；避免小改动重复生成 5 分 49 秒成片。
- 旧 passed 案例只读；迁移时复制最小源码和资产，不复制其 9.8GB 历史 bundle/cache。
- 根工作区当前没有可用的 Git 基线，暂不执行大范围 `git add/commit`。每个 Task 完成后在 `validation/checkpoints/task-XX.json` 保存输入哈希、产物和校验结果；将来建立安全 Git 基线后再按 Task 提交。

## 当前停止门

M1 已于 2026-09-11 完成并通过独立审计：来源预检、逐词对齐、原分辨率边界复核和节点账本均已落盘。当前冻结为 5 章、70 Shot、174 Beat、141 Node、110 Element、66 Boundary；详见 `workspace/cases/kimi-k3-full-000-349633/planning/M1-summary.md`。等待用户反馈后再进入 M2，当前不批量生成布局或动效代码。
