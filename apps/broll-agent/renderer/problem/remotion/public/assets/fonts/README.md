# 字体取证结论

本文件与 PNG 都只用于取证。所有候选均来自真实存在的字体文件；使用 Pillow 渲染原文案，直接解析字体 SFNT `name` 表保存家族名、PostScript 名与版权元数据。置信度表示视觉近似程度，并非精确识别的统计概率。各组源裁切与候选尽量按相近 ink 高度展示，不包含金属、阴影、RGB 色差或模糊，因此字体轮廓与效果应分开审阅。

## 推荐实现

| 分组 | 推荐家族 / PostScript 名 | 样式 | 置信度 | 主要差异 |
| --- | --- | --- | --- | --- |
| 解决问题 | YouSheBiaoTiHei / YouSheBiaoTiHei | normal 400；自带约 8° 斜角 | 0.96 | 与原字形高度一致；残余差异主要来自字号/字距与材质 |
| 真正困难 | Heiti SC / STHeitiSC-Light | normal 300 | 0.62 | 需大字距，细笔端点未唯一识别 |
| Truly difficult | Monaco / Monaco | normal 400 | 0.40 | 源字形有 OCR A 一类的方形负空间；本机候选不能精确恢复 |
| 新闻中文标题 | Songti SC / STSongti-SC-Bold | normal 700 | 0.72 | 微小收笔与字重不确定；英文建议单独 Times New Roman |
| 正文字幕 | Heiti SC / STHeitiSC-Light | normal 300；scaleX 约 0.85 | 0.68 | 原字幕明显偏窄；保持等粗白字并另加轻阴影 |
| 绿色提示词 | PingFang SC / PingFangSC-Medium | normal 500 | 0.72 | 微小笔画/重心不同；绿色渐变与光晕独立实现 |
| 表格拉丁名称 | Carlito / Carlito-Italic | italic 400 | 0.88 | 与 Calibri Italic 风格相近；未确认原片就是 Calibri |
| 表格数字 | Carlito / Carlito-Italic | italic 400 | 0.84 | 数字字宽与原片局部镜头变形可能有微差 |

`font-candidates.json` 保存每组 Top 3 的绝对文件路径、TTC index、名字元数据、理由、渲染参数和许可状态。macOS 内置字体宜通过 `local("PostScript 名")` 使用，未核实其跨设备分发许可，不将系统字体擅自包装成开放字体。

## Top 3 比较证据

- [超粗中文标题](hero-heavy-chinese-top3.png)：优设标题黑 0.96；兰亭黑 Heavy 0.49；冬青黑 W6 0.32。
- [上方细中文](hero-small-chinese-top3.png)：黑体简 Light 0.62；苹方 Light 0.57；冬青黑 W3 0.45。
- [下方拉丁小字](hero-small-latin-top3.png)：Monaco 0.40；Andale Mono 0.34；Menlo 0.30。
- [新闻宋体标题](news-serif-headline-top3.png)：宋体简 Bold 0.72；宋体简 Regular 0.61；STSong 0.51。
- [底部字幕](subtitle-body-top3.png)：黑体简 Light 0.68；苹方 Regular 0.57；冬青黑 W3 0.54。
- [绿色提示词](green-prompt-top3.png)：苹方 Medium 0.72；兰亭黑 Demibold 0.66；冬青黑 W6 0.56。
- [表格斜体名称](table-italic-latin-top3.png)：Carlito Italic 0.88；Arial Italic 0.52；Helvetica Neue Italic 0.46。
- [表格斜体数字](table-numerals-top3.png)：Carlito Italic 0.84；Arial Italic 0.59；Helvetica Neue Italic 0.52。

## 优设标题黑来源与限制

[优设官方发布页](https://www.uisdc.com/uisdc-first-free-font) 将该字体声明为“永久免费可商用字体”，并明确影视字幕、花字和片头等用途。页面同时说明与字由联合发布。已保存官方页面为 `uisdc-official.html`。

从官方页面 CSS `https://assets.uisdc.com/assets/2021/css/styles.css?v=4.6.13` 找到的 `YSBiaoTiHei.ttf` 只有 3,344 字节，是官网使用的极小子集，不能用于“解决问题”，因此不推荐运行时使用此文件。

最终通过联合发布方 [字由字体详情页](https://www.hellofont.cn/font-detail?fontid=7088) 的公开文字预览接口获取真实字体子集：

- 文件：`downloads/YouSheBiaoTiHei-official-preview.ttf`。
- 获取链：字由详情页 → 同站 `/dist/all.js` 中 `u.webfont` → `https://www.hellowebfont.com/cloudfontserver/webfontmanagement/webfontmanagerhandler.ashx` → 响应中的官方 `hellowebfonts.oss-cn-beijing.aliyuncs.com` 字体路径。
- 原接口响应：`hellofont-preview-response.json`；页面/脚本保留为 `hellofont-official.html`、`hellofont-all.js`。
- 字符覆盖：`解决问题突破边界探索可能真正困难0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz`。
- 当前默认“解决问题”与替换“突破边界”均完整覆盖。未取得完整 6,763 汉字版本；其它汉字需通过相同官方渠道补充后才能保持标题字形一致。应在主题/字体 props 保留此已知限制。
- 原片 `解` 顶部切角、`决` 的紧密空隙、`问` 顶部断开、`题` 的三角收笔与此字体高度吻合；与其它粗黑体存在明显差别。

标题 ink 拟合：在 Pillow 下以 202 px、无额外斜切、无描边渲染“解决问题”，ink 为 **743 × 147 px**，相对绘制原点 y 偏移 58 px。按源目标 x 277–1006 / y 282–429，使用约 `scaleX(0.9812)` 可得到 729 × 147 px。浏览器基线/行盒与 Pillow 不同，应以最终浏览器 still 的 ink 实测定位；不要把字号当成字面高度。

## Carlito 来源与许可

[Google Fonts 官方 Carlito 项目](https://github.com/googlefonts/carlito) 将 Carlito 描述为与 Calibri 度量兼容的字体。原参考表格具有单层斜体 a、圆点 i、l 弯尾，因此 Carlito Italic 明显优于 Arial/Helvetica 的双层 a、方点 i。该判断是基于轮廓比较的推断。

- 正式文件：`downloads/Carlito-Italic.ttf`，从 `https://raw.githubusercontent.com/google/fonts/main/ofl/carlito/Carlito-Italic.ttf` 下载。
- 许可：[官方 OFL](https://github.com/google/fonts/blob/main/ofl/carlito/OFL.txt)，已保存 `downloads/Carlito-OFL.txt`。可按 SIL OFL 1.1 随案例分发并保留许可证。
- 此为正式完整拉丁字体，区别于优设标题黑的预览子集。

未下载阿里妈妈数黑体：优设标题黑已经在关键字形上高度吻合，无必要继续扩大候选资产。
