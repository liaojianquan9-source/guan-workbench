# Designs.md · TO-DO Panel 视觉语言规格（迁往「观」）

> **用途**：把 TO-DO Panel 的 UI 设计语言（壳、色板、组件、交互节奏）抽象成可复现规格，供「观 / guan-workbench」吸收。  
> **不是**：把待办、剪贴板、密钥保险柜等业务功能整体搬进「观」。  
> **准绳**：精确 CSS 取值以 `renderer/styles.css` 的 `:root` 为准；`docs/DASHBOARD-DESIGN.md` 中 **§11 覆盖 §0–§10**；产品截图与官网营销页用于核对布局与气质差异。

---

## 1. 文档目的与范围

### 1.1 要解决什么

「观」是本机 AI 视频工作台（拉片 / 复刻 / 制作 / 素材库）。当前原型偏「专业工具深色后台」，密度高、组件语言不统一。TO-DO Panel 提供了一套更克制的 **贴顶暗色浮层 + 胶囊 Tab + 玻璃 tile + 单色体系**，适合作为「观」下一轮视觉与壳层参考。

### 1.2 范围内

| 吸收 | 说明 |
|------|------|
| 产品壳气质 | 深色单色、发丝边、顶部高光、圆角浮层面板 |
| Tab 胶囊导航 | 左主右次、激活浅色填充、一壳一职 |
| Tile / Bento 材质 | `surface-*` 分层、hairline、inset 高光 |
| 输入与 CTA | 回车提交、白胶囊主按钮、聚焦环 |
| 列表→详情双栏 | 笔记/录制式：左列表右预览（可映射制作判断队列） |
| Token 体系 | 颜色 / 圆角 / 间距 / 字号 / 动效变量化，禁止散落硬编码 |

### 1.3 范围外（明确不复制）

- 贴顶刘海 / Dynamic Island 折叠展开的**产品形态**（「观」是浏览器本机工作台，不是菜单栏浮层）
- 待办四象限、剪贴板历史、系统剪贴写回、密钥保险柜、本机应用启动坞、摄像头镜子等**业务**
- 官网营销页的 Kanit 大标题、霓虹 CTA 渐变、滚动叙事（仅作气质对照）
- 把 TO-DO Panel 的 Tab 集合原样塞进「观」侧栏

---

## 2. 产品壳与信息架构

### 2.1 产品形态（对照，非照搬）

| 项 | TO-DO Panel | 「观」应对 |
|----|-------------|-----------|
| 运行时 | Electron 原生，Mac/Windows | 本机浏览器工作台（4182） |
| 壳 | 屏幕顶部居中浮层，折叠≈刘海，展开=圆角面板 | 保持全页工作台；可吸收「单一壳 + 顶栏胶囊」而非贴顶折叠 |
| 隐喻 | Dynamic Island：需要时展开，用完收起 | 「观」用视图切换 / 面板折叠即可，不必模仿刘海动画 |
| 内容尺寸（§11） | 各 Tab 统一约 `1120 × 540` 内容区 | 「观」按自身布局；制作四区可参考其疏密，不锁死像素 |

### 2.2 Tab 地图（当前产品 UI，以截图为准）

截图证据：`todo-panel-ui/product/*.webp|jpg`。顶栏分左右两组胶囊：

**左侧 · 主工作区（更醒目）**

| Tab | 文案 | 一句话职责 | 布局骨架 |
|-----|------|------------|----------|
| 首页 | 首页 | 一日总览 bento | 多尺寸 tile 拼贴（媒体 / 计时 / 照片 / 当前窗口 / 快速录音 / 常用指令 / 随笔记） |
| 待办 | 待办 | 多工作流清单 | 2×2 tile；每格色点 + 列表 + 底栏「回车保存」输入 |
| 剪贴 | 剪贴 | 剪贴历史 | 顶滤芯片 + 瀑布/网格卡片；选中=浅色反相 |
| 笔记 | 笔记 | 笔记读写 | 左列表 + 右编辑器 |

**右侧 · 次级工具（更安静）**

| Tab | 文案 | 一句话职责 | 布局骨架 |
|-----|------|------------|----------|
| 链接 | 链接 | 分组书签 | 顶「粘贴网址回车」+ 2×2 分组 tile |
| 录制 | 录制 | 录音库 + 转写 | 左库列表 + 右播放器/转写；白条播放器 + 白胶囊「录音」CTA |
| 密钥 | 密钥 | 本机保险柜 | 左新增表单 + 右账号网格；白胶囊「保存」 |

> **与文档演进的差异**：`DASHBOARD-DESIGN` §0/§11 早期记的是「四 Tab / 应用页」等演进态；**现行产品截图**已扩展为上表七区（笔记独立、链接/录制/密钥在右）。迁「观」时以**截图的导航分列 + 一壳一职**为 IA 参考，不以过时章节的 Tab 数量为准。

### 2.3 壳层结构（抽象）

```
PanelShell（深底 + hairline + 可选虹彩外缘）
├─ TopChrome
│   ├─ PrimaryPills[]     ← 左：主职
│   └─ SecondaryPills[]   ← 右：次职（更淡）
└─ Workspace（当前 Tab 独占；同一时刻只干一件事）
```

原则：**一个壳、一个激活 Tab、一套选中态语言**。

---

## 3. Design Tokens

### 3.1 取值优先级（冲突时）

1. **`renderer/styles.css` `:root`** —— 实现真相  
2. **`docs/DASHBOARD-DESIGN.md` §11** —— 覆盖 §0–§10 的产品约束叙述  
3. **§1 历史表** —— 仅作演进说明；若与 styles.css 冲突（例如表面色从 `rgba` 改为实色 hex），**以 styles.css 为准**  
4. **官网 landing CSS** —— 营销页专用，不进产品 `:root`  
5. **产品截图测量** —— 用于「虹彩外缘 / 炭灰观感」等文档未写死的氛围描述

### 3.2 产品色（`styles.css` `:root`）

#### 颜色 · 黑白灰主体

```
--bg-base:            #000000;
--surface-1:          #111111;
--surface-2:          #191919;
--surface-3:          #252525;
--hairline:           rgba(255, 255, 255, 0.08);
--hairline-soft:      rgba(255, 255, 255, 0.06);
--highlight-top:      rgba(255, 255, 255, 0.07);
--tile-highlight:     rgba(255, 255, 255, 0.05);
--squircle-highlight: rgba(255, 255, 255, 0.16);

--text-1:             #F5F5F5;
--text-2:             #A1A1A1;
--text-3:             #707070;
--text-4:             #4A4A4A;
--focus-ring:         #6EA8FF;

--scrollbar-thumb:        rgba(255, 255, 255, 0.08);
--scrollbar-thumb-hover:  rgba(255, 255, 255, 0.20);
--tooltip-bg:             rgba(0, 0, 0, 0.92);
--item-hover:             rgba(255, 255, 255, 0.04);
--panel-shadow:           rgba(0, 0, 0, 0.42);
```

#### 少量状态色（大面积仍单色）

```
--accent-green:  #30D978;
--accent-orange: #FF9352;
--accent-blue:   #438CFF;
--p0:            #FF5F57;          /* 红 */
--p1:            var(--accent-orange);
--p2:            var(--accent-green);
--p3:            var(--accent-blue);
```

剪贴卡类型描边（§11：浅描边区分类型，不用左侧色条）：

```
--clip-text:          rgba(255, 255, 255, 0.18);
--clip-url:           var(--accent-blue);
--clip-image:         var(--accent-orange);
--clip-border-text:   rgba(255, 255, 255, 0.10);
--clip-border-url:    rgba(67, 140, 255, 0.22);
--clip-border-image:  rgba(255, 147, 82, 0.20);
--clip-card-h:        152px;
--clip-thumb-h:       120px;
--clip-meta-h:        30px;
```

#### 圆角

```
--r-notch:      10px;
--r-panel:      16px;
--r-tile:       18px;
--r-squircle:   12px;
--r-input:      10px;
--r-list-item:  12px;
--r-popover:    18px;
--r-pill:       999px;
```

> 截图中外层面板观感更圆（约 20–24px 级），实现仍以 `--r-panel: 16px` 与 tile `18px` 为准；「观」若要更软，可在自有 token 上把壳圆角提到 20–24px，但需单独命名，避免假装来自 TO-DO Panel。

#### 间距（8pt）

```
--hairline-w: 1px;
--scrollbar-w: 3px;
--s-half: 2px;
--s-1: 4px;  --s-2: 8px;  --s-3: 12px;
--s-4: 16px; --s-5: 20px; --s-6: 24px;
```

面板内边距约 `var(--s-2) var(--s-6) var(--s-4)`；tile 间距常用 `var(--s-3)`。

#### 字体 / 字号

```
--font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei',
        'SF Pro Display', 'SF Pro Text', 'PingFang SC', sans-serif;
--font-mono: 'SF Mono', ui-monospace, monospace;

--fs-micro: 9px;
--fs-caption: 10.5px;
--fs-small: 11px;
--fs-code: 11.5px;
--fs-ui: 12px;
--fs-body: 13px;
--fs-body-lg: 13.5px;
--fs-heading-3: 15px;
--fs-heading-2: 17px;
--fs-heading-1: 19px;
```

字重克制：UI 以 **400 / 500** 为主，避免无谓 600/700。数字用 `font-variant-numeric: tabular-nums`。

#### 动效（Motion · styles.css）

```
--ease:          cubic-bezier(0.25, 0.46, 0.45, 0.94);
--ease-out:      cubic-bezier(0.16, 1, 0.3, 1);
--ease-spring:   cubic-bezier(0.34, 1.1, 0.4, 1);
--ease-soft:     cubic-bezier(0.4, 0, 0.2, 1);
--ease-island:   cubic-bezier(0.22, 1, 0.36, 1);

--d-micro: 100ms;
--d-1:     90ms;
--d-fast:  140ms;
--d-base:  180ms;
--d-slow:  260ms;
--d-grand: 340ms;
```

原则：优先 `transform` / `opacity`；尊重 `prefers-reduced-motion`。

### 3.3 官网营销色（landing only · 勿混入产品 token）

来源：`https://xiaopu-ai.github.io/TO-DO-Panel/` 打包 CSS `:root`：

```
--page-bg:        #0c0c0c;
--surface:        #141416;
--surface-raised: #1b1b1f;
--silver:         #d7e2ea;
--muted:          #858b94;
--dim:            #565a62;
--line:           #d7e2ea2e;   /* ≈ rgba(215,226,234,0.18) */
--heading-a:      #646973;
--heading-b:      #bbccd7;
--cta-magenta:    #b600a8;
--cta-violet:     #7621b0;
--cta-orange:     #be4c00;
--ease-out:       cubic-bezier(0.22, 1, 0.36, 1);
```

Tab 叙事卡 accent（营销滚动区，非产品 `:root`）：`#ff665f` / `#ffad4d` / `#52d58a` / `#5b9cff` / `#ff5c7c` / `#9d7cff`。

### 3.4 营销色 vs 产品色 · 差异说明

| 维度 | 官网 Landing | 产品 `styles.css` | 截图观感 |
|------|--------------|-------------------|----------|
| 底色 | `#0c0c0c` 偏炭灰 | `#000000` OLED 纯黑 | 浮层外缘旁常显约 `#101018` 炭灰环境 |
| 表面 | `#141416` / `#1b1b1f` | `#111` / `#191` / `#252` 三级 | tile 略亮于纯黑底 |
| 主文 | `--silver #d7e2ea` | `--text-1 #F5F5F5` | 产品更「白」、营销更「银」 |
| 强调 | 品红/紫/橙 CTA 渐变、大号 Kanit | 仅 P0–P3 / accent 点缀 + 白胶囊 CTA | 产品极克制 |
| 外缘 | 营销卡 `1px solid var(--line)` | hairline + inset 高光 | 截图常见**细虹彩/微亮外缘**（氛围，非独立 token） |

**「观」建议**：产品面跟 `styles.css` 单色体系；若要更「浮层感」，可在壳上加 `1px` hairline + 极轻外阴影，**不要**上官网 CTA 霓虹渐变。

---

## 4. 材质与组件

### 4.1 Panel（展开壳）

文档配方（§2，仍与实现精神一致）：

```
background: var(--bg-base);
border: 1px solid var(--hairline);
/* 贴顶形态时 border-top: none；「观」全页壳可四边 hairline */
border-radius: … var(--r-panel);
box-shadow: 0 26px 60px rgba(0,0,0,0.6), inset 0 1px 0 var(--highlight-top);
```

截图补充：外缘可有极轻虹彩/微亮，保持暗、薄、不抢内容。

### 4.2 Tile（模块块）

```
background: var(--surface-1);
border: 1px solid var(--hairline);
border-radius: var(--r-tile);
box-shadow: inset 0 1px 0 var(--tile-highlight);
```

hover → `background: var(--surface-2)`（时长 `--d-base` / `--d-fast`）。

### 4.3 Pill（Tab / 滤芯 / CTA）

| 态 | 视觉 |
|----|------|
| 主 Tab 未激活 | 深底 + 浅字 `--text-2/--text-3`，可选细描边 |
| 主 Tab 激活 | **浅色实心胶囊**（近白/浅灰），深色图标与字；对比最强 |
| 次 Tab | 同 pill 形，但更淡、更小视觉权重 |
| 滤芯片（剪贴「全部/文字/图片/收藏」） | 更小 pill；激活略亮 |
| Primary CTA | **白底黑字**圆角胶囊（录制「录音」、密钥「保存」） |

圆角一律 `--r-pill: 999px`。

### 4.4 Input

- 底 `--surface-1`，聚焦抬到 `--surface-3` 或 `--focus-ring` 描边（密钥表单可见蓝聚焦环 `#6EA8FF`）
- 圆角 `--r-input: 10px`；全宽条可更接近 pill
- 占位 `--text-4`；正文 `--text-1`
- **回车 = 提交**（待办新增、链接粘贴、常用指令保存）

### 4.5 Squircle / 图标钮

```
border-radius: var(--r-squircle);
box-shadow: inset 0 1px 0 var(--squircle-highlight);
```

应用图标在现行产品中倾向「原样展示、少包壳」（演进记录 §10.5）；「观」素材缩略图可学「少装饰、让内容本身说话」。

### 4.6 Bento

首页：不规则多 tile 拼贴，**统一材质、不同尺寸**。  
待办 / 链接：规则 2×2。  
笔记 / 录制 / 密钥：双栏（列表 | 详情/表单）。

---

## 5. 各 Tab 布局规格（对照 product 截图）

截图目录：`/workspace/todo-panel-ui/product/`。

### 5.1 首页 · `home.jpg`

- **顶栏**：左四主 pill，右三次 pill；「首页」浅色激活。
- **Bento 块（所见）**：
  - 左上：正在播放（封面 + 控件）
  - 其旁：计时器，**橙色环**强调（`--accent-orange` 系点缀，非大面积染色）
  - 左下：竖幅照片 tile
  - 中上：「当前窗口」应用图标网格
  - 中下：「常用指令」——输入「回车保存」+ 列表项
  - 右中：「快速录音」——时长 + 红点录制控件
  - 最右：「随笔记」—— Markdown 占位大竖栏
- **迁「观」启发**：仪表盘用 bento 做「今日状态」可以，但块要映射视频作业（在跑任务、最近成片、待确认段），不要抄媒体播放器/镜子。

### 5.2 待办 · `todo.webp`

- 2×2 工作流 tile；每格：
  - 标题前 **色点**（红/橙/绿/蓝 = P0–P3 token）
  - 右上计数
  - 列表项：圆勾选、文案、可选进度胶囊、时间、删除
  - 底栏输入：「添加待办，回车保存…」+ 可选日期钮
- §11：矩阵 2×2；单次回车新增；色点红/橙/绿/蓝。

### 5.3 剪贴 · `clipboard.webp`

- 顶：类型滤芯 pill（全部 / 文字 / 图片 / 收藏）+ 右侧清理
- 内容：多列卡片网格/瀑布；§11 规定等高卡 `--clip-card-h: 152px`，过长截断
- 类型靠**浅描边**区分（见 clip border token），无左侧色条、无冗余类型大标签
- 选中卡：浅底反相，成为最强焦点

### 5.4 笔记 · `notes.webp`

- 左：「笔记本」标题 + 篇数 + 搜索 + 笔记卡片列表（选中浅描边/略亮底）
- 右：大编辑面——标题、`已保存 · 时间`、正文；右上弱删除
- **最适合映射「观」制作左队列 + 中预览的双栏节奏**

### 5.5 链接 · `links.webp`

- 顶全宽输入：「粘贴网址并回车，自动读取标题与分类…」
- 下方 2×2 分组 tile：组名、计数、+ / 删除；组内 favicon + 标题 + URL 次文

### 5.6 录制 · `recordings.webp`

- 左库：「录音资料库」+ 计数；次钮「API 配置」+ **白胶囊「录音」**
- 右：标题/元信息 → **白条播放器** →「转写文本」区（复制/导出/删除）
- 选中列表项可带微紫/靛描边（截图所见；实现若无独立 token，迁「观」时用 `--surface-3` + hairline 即可，勿发明新品牌色）

### 5.7 密钥 · `credentials.webp`

- 左：新增表单（软件/账号/密码）+ 绿「安全存储」徽标 + 白「保存」
- 右：账号网格卡（名/账号/掩码 + 账号·密码·修改）
- **「观」不吸收此业务**；只学表单层级与白 CTA。

---

## 6. 交互模式

| 模式 | 规格 | 「观」可复用点 |
|------|------|----------------|
| 展开 / 收起 | 刘海垂下落定（`--d-grand` + `--ease-island`）；收起更快 | 侧栏/抽屉可用同曲线，不必贴顶 |
| Tab 切换 | 一壳只显一职；激活 pill 浅填充；内容交叉淡入 | 侧栏或顶栏视图切换 |
| 回车提交 | 待办/链接/指令等 Enter 保存；忽略 IME `isComposing` | 审批备注、标签、快速替换确认 |
| 选中态 | 列表项/卡片：略亮底或反相；与激活 Tab 同属「浅色=焦点」家族 | 制作队列当前段、素材库选中 |
| 主按钮 | 白胶囊 CTA | 「确认进成片」「批准入库」 |
| 悬停微动 | tile 轻抬、按钮 `:active` 缩小 | 克制使用，避免花哨 |
| 空态 | 短句 + 指向下一步（非大插画墙） | 复刻空态、素材空库 |
| 无障碍 | `focus-ring`；`prefers-reduced-motion` | 必须保留 |

---

## 7. 「观」迁移映射建议

### 7.1 应吸收（视觉语言 / 零件）

| TO-DO Panel | 落到「观」 |
|-------------|-----------|
| 深色单色 + hairline + 顶高光 | 统一 4182 工作台 token，替换散落灰阶 |
| 左主右次胶囊 / 分段激活 | 顶栏或精简侧栏：素材 / 拉片 / 复刻 / 制作；激活浅胶囊 |
| Tile 玻璃材质 | 判断卡、样式卡、素材卡、预览外框 |
| 白胶囊 Primary CTA | 「确认」「批准」「开始渲染」 |
| 笔记式双栏 | **AI 制作**：左判断队列 · 中预览（右决策可第三栏） |
| 待办色点语义 | 仅用于状态点（通过/待定/风险），不大面积染色 |
| 回车提交 + 清晰选中态 | 贯穿复刻批准与制作确认 |
| 一壳一职 | 每个主视图只做一类决策，避免向导表单与时间线抢权 |

### 7.2 不要照搬

| 不要 | 原因 |
|------|------|
| 贴顶刘海 / 折叠岛 | 「观」是常驻工作台，不是菜单栏工具 |
| 密钥保险柜、剪贴板上屏、系统启动坞 | 业务无关；且密钥类涉及安全边界 |
| 官网 Kanit 巨字、CTA 霓虹渐变 | 营销气质 ≠ 产品克制单色 |
| 首页镜子 / 汽水音乐块 | 与视频生产主线无关 |
| 把七个 Tab 原样塞进侧栏 | 「观」主线是拉片·复刻·制作·素材，Tab 应映射自身 IA |
| 无确认自动成片等「省事」交互 | 与「观」人工闸门原则冲突 |

### 7.3 建议落地顺序（设计侧）

1. **Token 对齐**：在「观」建立与上表等价的 CSS 变量（可前缀 `--guan-`，值对齐 styles.css）。  
2. **壳与导航**：顶栏/侧栏改胶囊激活态；去掉多余一级入口。  
3. **制作四区**：用笔记/录制双栏节奏重排「列表 · 预览 · 决策 · 时间线」。  
4. **复刻 / 素材卡**：统一 tile + 选中 + 白 CTA。  
5. **最后**再考虑装饰性虹彩外缘与动效细化。

---

## 8. 证据与来源

### 8.1 官方仓库与文档

| 资源 | 链接 |
|------|------|
| 仓库 | https://github.com/xiaopu-ai/TO-DO-Panel |
| 仪表盘设计规格 | https://github.com/xiaopu-ai/TO-DO-Panel/blob/main/docs/DASHBOARD-DESIGN.md （**§11 优先于 §0–§10**） |
| 实现真相 CSS | https://github.com/xiaopu-ai/TO-DO-Panel/blob/main/renderer/styles.css （`:root`） |
| 产品说明 | https://github.com/xiaopu-ai/TO-DO-Panel/blob/main/README.md |
| 官网（营销） | https://xiaopu-ai.github.io/TO-DO-Panel/ |

说明：仓库内**无**名为 `Designs.md` 的文件；最接近的正式设计文即 `docs/DASHBOARD-DESIGN.md`。

### 8.2 本机截图证据

```
/workspace/todo-panel-ui/product/home.jpg
/workspace/todo-panel-ui/product/todo.webp
/workspace/todo-panel-ui/product/clipboard.webp
/workspace/todo-panel-ui/product/notes.webp
/workspace/todo-panel-ui/product/links.webp
/workspace/todo-panel-ui/product/recordings.webp
/workspace/todo-panel-ui/product/credentials.webp
/workspace/todo-panel-ui/screens/   ← 官网滚动区与导航裁切
```

### 8.3 ComputerUse / 调研摘要（已核对截图）

- 原生 Electron；官网仅为营销落地页。  
- 产品 = 顶栏居中深色浮层（Dynamic Island 隐喻）。  
- Chrome：左 首页/待办/剪贴/笔记；右 链接/录制/密钥；激活 = 浅填充 pill。  
- 模式：一壳一职、可展开收起、深色 + hairline + 每区至多一处强调色、回车保存、白胶囊主 CTA。  
- 产品观感近炭灰环境 + 虹彩细缘；营销 token 以 `--page-bg #0c0c0c` 等为准，与产品 `:root` 分离。

### 8.4 本文文件位置

- `/workspace/Designs.md`（主交付）  
- `/workspace/todo-panel-ui/Designs.md`（副本，与截图目录同树）

---

*生成说明：色值与圆角/动效均引自 `renderer/styles.css` `:root` 或官网 landing CSS；布局描述对照 product 截图与 DASHBOARD-DESIGN §11。未虚构未在源中出现的 hex。*
