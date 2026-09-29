# Kimi · 图文与比较源码包

本包来自已有 Kimi 动态复刻案例，包含实际 Remotion 源码、布局、动效、图片和字体资源及替换参数示例。没有成片、原始参考视频、对照视频或完整取证文件；成片请在 B-roll 样式库案例页另行查看或下载。

## 本地运行

需要 Node.js、npm 和 Chrome/Chromium。解压后进入 `remotion` 目录：

```sh
npm install
npm run typecheck
npm run studio
```

需导出时在 `remotion` 目录执行：

```sh
npx remotion render composition.tsx LjqBrollCase ../output/generated.mp4 --public-dir=public --codec=h264 --muted --concurrency=1 --browser-executable="/absolute/path/to/chrome"
```

macOS 常见浏览器路径：`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。输出写入新的 `output/` 目录。画面为 1280×720、30fps、428帧、14秒8帧，无音轨。原参考范围为 00:00:20:04–00:00:34:12。

## 修改入口

- `remotion/composition.tsx`：实际入口及默认参数。
- `remotion/editable-case.tsx`：标题、正文、提示词、表格、背景图片与图层。
- `remotion/schema.ts`：可修改参数约定。
- `specs/layout.json`：稳定元素ID、内容与场景结构。
- `specs/motion.json`、`specs/motion-bindings.json`、`remotion/motion-runtime.tsx`：逐帧动效及图层绑定。
- `examples/replacement-motion-props.json`：已有换字、换数字、配色和背景图示例。导出命令追加 `--props=../examples/replacement-motion-props.json` 使用该参数。

`content` 修改文字，`numbers` 修改数字，`assets['problem-background']` 修改单张背景图，`theme`/`colors` 修改配色，`fonts` 修改字体。提示词的 `prompt-card` 与 `prompt-plain` 是同一连续画面中的两组元素，修改文字时应同步两组。`sceneId` 可用于选择场景，当前动效仍沿用完整连续时轴，并不代表每一段已经独立封装。

## 关联的早期标题模板

`examples/title-highlight-template.json` 是同一 Kimi 文章标题形式的早期模板：整句标题与独立高亮底通过差值混合产生变色。本例实际运行入口没有加载该 JSON；它仅作为关联参考，不应替换当前的 layout/motion 文件。

## 状态与素材

已完成动态复刻与替换检查；自动保真 QA 仍待审。已知少量字体、正文和光学效果差异。默认使用了部分 macOS 系统字体，系统字体未随包分发；换电脑需提供同字体或通过 fonts 指定替代并重新检查。

`remotion/public/assets/fonts/YouSheBiaoTiHei.ttf` 是已有官方预览子集，默认“解决问题”和测试“突破边界”覆盖，但任意新汉字可能回退。Carlito 许可在相同目录的 `Carlito-OFL.txt`。字体来源与限制见 `remotion/public/assets/fonts/README.md`。其中旧取证图片链接不在本包范围。

背景图片来源见 `assets/found/README.md` 及 `evidence/asset-sources/problem-background.json`。本包仅为本地案例整理；第三方素材与字体原有许可不因打包而改变。布局与动效中的取证路径仍保留历史记录，完整验收证据未包含。
