# Kimi · 标题与参数页源码包

本包来自已有 Kimi 0–11 秒复刻案例，包含实际 Remotion 源码、逐帧动效参数、元素摘要和独立月面素材。没有成片、原始参考视频、对照视频或完整取证文件；成片请在 B-roll 样式库案例页另行查看或下载。

## 本地运行

需要 Node.js、npm 和 Chrome/Chromium。解压后在本文件所在目录执行：

```sh
npm ci
npm run still -- --browser-executable="/absolute/path/to/chrome"
npm run render -- --browser-executable="/absolute/path/to/chrome"
```

macOS 常见浏览器路径：`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。输出写入新建的 `output/` 目录。画面为 1280×720、30fps、330帧、11秒。

## 修改入口

- `remotion/composition.tsx`：实际画面组件及默认参数。
- `remotion/schema.ts`：文案、数字、单位、字体、配色、月球图片等参数。
- `remotion/motion-state.tsx` 与 `specs/motion.json`：连续动效与逐字行为。
- `elements.json`：元素摘要，不是完整案例验收合同。
- 示例：将 still 命令追加 `--props='{"motionEnabled":false,"kimiTitle":"EDITABLE"}'` 可检查静态替换。

原项目使用本机的 Songti SC、Impact、Helvetica Neue、Savoye LET 等字体，系统字体未随包分发。换电脑或改字体后需重新检查文字尺寸与换行。原项目未提供 tsconfig.json，本包保留原始构建结构。

## 状态与范围

用户已认可整体观感；自动保真 QA 仍待审。口播人物区域按原约定留白，片尾纯白不是漏渲染。当前是一个连续案例，并未将每个镜头分别封装成独立调用的成片。

月球素材来源与署名见 `remotion/public/moon/SOURCES.md`。本包仅为本地案例整理；第三方素材与字体的原有许可不因打包而改变。`motion.json` 中的取证路径仅作历史溯源，其文件未全部包含在本包。
