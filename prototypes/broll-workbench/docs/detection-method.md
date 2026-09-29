# 拉片处理方式

参考拉片宝公开版本 Pro 1.2（7fe612c5f4947f6222eaaf4e7ae19d68cd9ac76f）的源码取证。在本工程独立实现，没有复制其 Swift 界面代码。

镜头检测使用 `transnetv2-pytorch==1.0.5`，本地 CPU 推理。FFmpeg 解码连续画面；阈值 0.35；最短镜头 `max(0.3, 8 / fps)`。切点整理为完整覆盖视频的相邻时间段，缩略图选开始后约 0.08 秒、最多至镜头中点。保留原视频，不自动分割成多个视频文件。主动选择 `--detector ffmpeg` 才使用另一个检测算法，并在结果中明确标记；模型失败不会静默切换算法。

字幕由 whisper.cpp v1.8.3 的 large-v3-turbo q5_0 本地模型生成，优先 Metal，初始化失败回退 CPU。音频通过 FFmpeg 转为 16 kHz 单声道，做高低通和响度处理。结果保留时间戳，支持跳转与导出。识别内容可能出错，需回听核对。

歌曲识别由 shazamio 0.8.1 对 12 秒音频片段在本机生成指纹，再联网向 Shazam 查询；最多 12 个采样点、总时限 120 秒。匹配歌名后 iTunes 补充资料，不需要模型 API Key，不下载歌曲或视频。采样位置不是连续音乐区间；不推断音乐持续时长。

波形来自 PCM 峰值；画面六色色板来自 3 × 2 区域的平均颜色。以上无需大语言模型。

原始源码取证位于工程根 `outputs/shotpal-full-review-20260917/research/`。第三方实现来源：
- https://github.com/soCzech/TransNetV2
- https://pypi.org/project/transnetv2-pytorch/
- https://github.com/ggml-org/whisper.cpp
- https://github.com/shazamio/ShazamIO
