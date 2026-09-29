# 真实口播与跨项目复用验收

2026-09-21。唯一产品入口为 [现有工作台 → AI 制作](http://127.0.0.1:4182/?view=ai-making)。本次只通过该入口的 `/api/production/*` 调用制作 API，创建名为 **验收副本 · 跨项目复用** 的独立项目，保留原项目。

**结论：两卡批量改字、带口播声音的实际画幅审看、固定样式跨项目复用、验收批准与完整合成均已真实跑通。视觉产品效果尚未获用户确认。** 横版样式在竖屏里仅占约 31.6% 高度，上下大面积深色留边；这是已发现的产品效果问题，不因技术检查通过而获得认可。

## 使用与审看

打开上述入口，在制作项目中选择“验收副本 · 跨项目复用”。两张卡片的批准来自 `acceptance-test`，只用于验收，不代表用户审美选择，不进入用户偏好记忆。

- [完整 53 秒成片（通过工作台代理）](http://127.0.0.1:4182/api/production/files/55f721ea649548f09828381ed1666a6f/final-63583a8d577a4c2d9ebed2be4b8f2a5a.mp4)
- [c004 实际竖屏带音预览](http://127.0.0.1:4182/api/production/files/55f721ea649548f09828381ed1666a6f/864a346092fe4b1fa701b9bc4c916f40.mp4) / [静帧](http://127.0.0.1:4182/api/production/files/55f721ea649548f09828381ed1666a6f/864a346092fe4b1fa701b9bc4c916f40.jpg)
- [c007 实际竖屏带音预览](http://127.0.0.1:4182/api/production/files/55f721ea649548f09828381ed1666a6f/07621d577d804466a8d05317c01ad98a.mp4) / [静帧](http://127.0.0.1:4182/api/production/files/55f721ea649548f09828381ed1666a6f/07621d577d804466a8d05317c01ad98a.jpg)

真实成片文件：

`/Users/liaojianquan/Documents/BrollProjects/files/55f721ea649548f09828381ed1666a6f/final-63583a8d577a4c2d9ebed2be4b8f2a5a.mp4`

## 项目与不可变资产证据

| 对象 | 本次实际引用 |
|---|---|
| 原项目 | `23db4d3f88134c4fb51d0fd54d346698`，revision 8 |
| 验收副本 | `55f721ea649548f09828381ed1666a6f`，验收后 revision 15 |
| 副本来源 | `derived_from={project_id:23db4d3f88134c4fb51d0fd54d346698,revision:8}` |
| 原项目与副本的口播 | `37ee83e1-c8af-4ab2-ae70-449ceac4c4fd@1`，`01-粗剪_无字幕.mov` |
| 原项目 c004 与副本 c004、c007 的共享样式 | `style-kimi-moon-v1@1`，月球质感主标题 |
| 复刻来源 | `replica-kimi-opening-v1@1`；参考源 `source-kimi-opening-v1@1` |
| 样式状态 | `technical_status=passed`；`fidelity_status=needs_review` |

两个项目的 source 引用与 c004 样式引用严格相同。副本没有复制出另一套样式身份，也没有修改共享资产。两次实际渲染均从共享资产中的不可变执行包恢复源码，报告 `source_origin=immutable_asset_package`，检查实际运行清单哈希。接受新字段后，最终交付保存卡片 fingerprint 与固定样式版本，而不是临时查找“最新样式”。

SHA-256：

| 证据 | 哈希 |
|---|---|
| 真实口播文件 | `53036531617a70470137f2c1c01336d845e723acc26255f0e32a94a134894fd8` |
| 共享样式执行包 | `81d1cf14ebc8649aa926dfa5d3cb4335ebe1f421e8217e87cae79db663ac803c` |
| 固定源码清单 | `3e1d1de36f5df5853c049d2c16d70a503c9a4dc7a8bf1430f92c3b395e8ae36e` |
| 原项目验收前后完整 JSON 的规范化哈希 | `e380a36e613b78ee0ce56b15ac77fe4ce4972eb66350fa5e63d8937586481efa` |
| 本次最终 MP4 | `4b742a3d5f808ff44cbb73c1190ca5ea424e521fa3c1511401d8c045e028f439` |

原项目前后完整 JSON 相同，仍是 revision 8；副本未选中的六张卡片也逐字段相同。源片许可状态仍是用户提供、未经独立许可核实、限本地项目；本次验收没有改变权利标记。

## 批量操作与字段进入输出的证据

| 卡片 | 口播范围 | 主标题 | 副标题 | 纹理字 | 最终渲染 fingerprint |
|---|---|---|---|---|---|
| c004 | 23.40–27.80 秒 | 睡好觉 | 用好AI | 好好休息 | `4f31b16d90bd91375e96f2d1ba921366a35d9e09971f92026a49810ebf0b0f49` |
| c007 | 39.34–46.30 秒 | 收工 | 明天 | 好好休息 | `0d347f226ae14ed2f10721abf5b9a1e4aeceda146c811c8ff863ff75f57c7ba7` |

c004 原先过长的副标题在原项目本轮 Agent 修订后已为“用好AI”；本验收显式保留该四字符文案。c007 的月球样式选择是验收设定，原 Agent 对该段的决定是保留口播。

不仅调用了批量 API，还验证了实际状态变化：副本 revision 9 两卡为 approved；对两卡一起改成“待替换纹理”后 revision 10 两卡均为 draft，旧渲染路径与 fingerprint 被移除；再一起改回“好好休息”得到 revision 11。此时立刻尝试批量批准返回 HTTP 400，项目版本未增加。随后批量重新预览、批量批准，才能最终合成。

真实预览任务 `61597dd114d34ecaaa9ec2ca0c21be81` 与真实合成任务 `79227c5d7418415abe9b1488b10531f3` 均完成。两次字段替换都使用 `card_ids=[c004,c007]`；所有批量历史的 actor 均为 `acceptance-test`。更早的首轮验收输出留在项目 deliveries 与证据目录中，没有用新输出覆盖旧文件。

渲染报告中 `fields` 与当前卡片字段逐项相同；真正送入 Remotion 的 `kimiTitle / k3Title / moonTitle` 分别等于主标题、副标题、纹理字。副本真实视频的 SHA-256：

| 卡片 | 原生 1280×720 渲染 | 带口播上下文的 1080×1920 预览 |
|---|---|---|
| c004 | `708d4921ead60e67dc9e4812ee04eeb426f4fa6fd4355d7385082bb671c7c407` | `526c8a1709cdb6048cdb3e046209cb72ca201a35f959ae399bede757cb49ba0a` |
| c007 | `96a66e543a3715eaf44a4fde4d199dee68845c89072c149f8c7ff8e45150c22f` | `fb0ff2619b9069f90308e668797f5cde35878534e106795d049f596308de6475` |

## 媒体验证与视觉限制

| 检查 | 结果 |
|---|---|
| 原片 / 成片画幅 | 均为 1080×1920 |
| 原片 / 成片帧率、帧数 | 均为 30 fps、1591 帧 |
| 原片 / 成片视频时长 | 53.033333 / 53.033008 秒，差 0.325 毫秒 |
| 成片音轨 | AAC、44.1 kHz、双声道，原音轨复制 |
| 完整音轨解码比较 | 原片和成片的 PCM SHA-256 都为 `2ffcb1d8fdc740918c4f5d9c899f1f9ed0506cb2be0bae73b3640fa672ad431a` |
| 完整 MP4 解码 | FFmpeg 无错误 |
| 最终文件大小与 Range | 31,187,048 字节；4182 返回 `206`、`bytes 0-1023/31187048`，内容与保存文件前 1024 字节完全相同 |
| 口播资产 Range | 4182 返回 `206`、`bytes 0-1023/78414436`，内容与源文件一致 |
| 审看预览 | c004 为 4.4 秒；c007 视频 6.933333 秒、音频 6.96 秒，视频误差少于一帧 |

已经人工查看成片 10.0、25.8、43.8、50.0 秒抽帧：未插入位置保留人物口播；两个插入位置显示各自替换标题，结尾恢复人物口播。每张卡片的实际竖屏预览也已检查。

仍需明确区分：

- 1280×720 内容适配竖屏采取保持全画面比例、居中深色补边。内容只有约 608 / 1920 = 31.6% 的高度。技术上保留了构图，产品效果存在明显大留黑问题；本次不把它当作已经成立的竖屏设计。
- Chrome 字体检查表明中文主、副标题实际使用 PingFang SC；混合副标题的英文使用 Helvetica Neue；纹理字使用 Songti SC。字体确实加载且可显示，字形与原参考有差异，报告保留回退提示。
- 四字符“用好AI”通过已知固定框的保守版式门。这个门只能排除确定的过度挤压，不能证明所有画面在手机上都足够好看。
- 复刻保真始终为 `needs_review`。本次验收批准只证明制作链路，不替用户决定最终样式、留黑或 B-roll 取舍。

## 复跑与证据位置

真实验收器为 `apps/broll-agent/tools/verify_real_production.py`。业务动作全部发往现有工作台 HTTP 代理；本地只写独立证据、读取产品返回的原生视频文件并运行媒体检查。它可恢复保存的任务编号，不因为重新执行而重复创建副本。新证据目录会创建一个新验收副本；已有目录默认继续其进度。

本次证据目录：

`/Users/liaojianquan/Documents/BrollProjects/acceptance/20260921-two-card/`

其中 `result.json` 汇总身份、哈希、媒体报告与输出路径，`http.jsonl` 保存实际请求日志，`original-before/after.json` 证明原项目未改，`clone-*-batch-replacement.json` 保存批量状态变化，`job-*.json` 保存任务结果，`cards-evidence.json` 绑定字段与实际输出。`final-c004-replacement.jpg`、`final-c007-replacement.jpg` 等为最终文件抽帧。视频与大文件保留在数据目录，不提交 Git。

只读复核，不重复改项目：

```sh
python3 apps/broll-agent/tools/verify_real_production.py \
  --evidence '/Users/liaojianquan/Documents/BrollProjects/acceptance/20260921-two-card' \
  --check-only
```

该模式禁止所有 POST。如果项目或引用后来改变，它会报告差异，不将新状态冒充旧验收结果。首次实际执行与只读复跑均通过。回归总门 `apps/broll-agent/verify.command`：62 个 Python 测试、20 个 Node 测试通过；日志位于证据目录 `verify-final.log`，只读复跑日志为 `check-only.log`。
