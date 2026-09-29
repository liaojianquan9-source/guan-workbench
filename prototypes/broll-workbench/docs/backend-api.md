# 本地拉片接口

服务默认地址 `http://127.0.0.1:4182`；静态页面目录 `public/`；项目存储 `data/`。不接受服务器文件路径，导入必须提交文件字节。

## 读取

- `GET /api/projects` → `{projects: [...]}`，按更新时间倒序，返回完整项目。
- `GET /api/projects/{id}` → 完整项目。
- `GET /media/{id}/source.mp4` → 可播放副本，支持 GET、HEAD、单段 `Range`、suffix range，不支持多段 range（416）。
- `GET /media/{id}/thumbnails/{shot_id}.jpg` → 真实关键帧。
- `GET /media/{id}/captures/{capture_id}.jpg` → 主动截图。
- `GET /media/{id}/audio/{clip_id}.m4a` → AAC 声音片段，也支持 Range。
- `GET /api/projects/{id}/waveform` → `{samples:[0..1真实峰值，1000项],duration,method:'pcm-peak',sample_rate:8000}`，缓存到本项目 waveform.json；没有音轨返回 422。
- `GET /api/projects/{id}/export?format=json|csv|md|docx|srt|txt` → 附件下载。DOCX 带真实嵌入缩略图、时长、重叠字幕、标签和笔记；SRT/TXT 导出已保存字幕。

## 修改

修改请求只接受同源浏览器来源；无 Origin 的本机非浏览器客户端可用于测试。Host 仅允许 `127.0.0.1:{port}` 或 `localhost:{port}`。不返回跨域允许头。

- `POST /api/projects?name=URL编码的文件名`，body 为视频原始字节，必须有 Content-Length。返回 201 完整项目。FFmpeg 可解码媒体转成 H.264/AAC 可播放副本，兼容 MP4 原样保留；无法解码返回 422 并清理失败上传。
- `POST /api/projects/{id}/analyze`，JSON `{threshold:0.35,min_duration:0.3,expected_revision?:整数}`。返回 202 完整项目。后台运行，轮询 GET 查看状态。
- `PATCH /api/projects/{id}/shots/{shot_id}`，JSON `{note?:文本,tag?:文本,expected_annotation_revision?:整数,expected_revision?:整数}`。只更新提交字段，返回 200 完整项目。
- `POST /api/projects/{id}/capture`，JSON `{time:来源秒}`。保存原尺寸 JPG 并加入 `captures`，返回 200 完整项目。
- `POST /api/projects/{id}/audio` 已下线，服务不再接收手动时间范围来新建 `audio_clips`。
- `POST /api/projects/{id}/transcribe`，JSON `{}`。启动本地字幕任务，返回 202 完整项目，读取 `project.transcript` 轮询。重复正在进行的任务返回 409。

重新分析应提交 `expected_revision`。笔记与标签保存应提交该草稿开始编辑时的 `expected_annotation_revision`，它优先检验单镜笔记版本，忽略项目其他后台进度变化；成功后该镜头 `annotation_revision` 加 1。未提交它的旧客户端仍按 `expected_revision` 校验。版本不符时返回 409，不覆盖数据。

分镜分析进行时拒绝笔记修改和重复分析；字幕任务状态独立，不阻止记录笔记。已有笔记或标签时拒绝重新分镜，避免覆盖。截图是追加动作，可以不提交项目版本；不再提供声音选区追加接口。

项目持久化字段（包括历史兼容字段）：

```json
{
  "captures": [{"id":"截图ID","time":2.5,"url":"/media/项目ID/captures/截图ID.jpg","created_at":"ISO时间","note":"","tag":""}],
  "audio_clips": [{"id":"片段ID","start":2,"end":5,"url":"/media/项目ID/audio/片段ID.m4a","duration":3.03,"created_at":"ISO时间","note":"","tag":""}],
  "transcript": {"status":"ready","progress":1,"message":"识别状态提示","engine":"whisper.cpp-large-v3-turbo-q5_0","language":"zh","segments":[{"start":0.6,"end":2.1,"text":"字幕文本"}]}
}
```

字幕状态 `idle | processing | ready | error`，排队也使用 processing；与主项目分镜状态独立。失败、重启或中断保留之前成功的字幕，允许重试。分镜与字幕共用一个本地模型推理名额，避免多模型同时占满资源。旧项目中的 `audio_clips` 继续返回，其媒体可读取，也可通过通用素材接口编辑标签或软删除。历史 AAC 文件保留来源 `start` / `end` 与实际 `duration`，以兼容编码后的少量采样帧差异。

## 项目格式

```json
{
  "id": "32位十六进制ID",
  "name": "视频.mp4",
  "duration": 337.066667,
  "fps": 30,
  "width": 852,
  "height": 480,
  "video_url": "/media/项目ID/source.mp4",
  "status": "ready",
  "progress": 1,
  "message": "处理结果提示",
  "shots": [{"id": "镜头ID", "start": 0, "end": 3.2, "thumbnail_url": "/media/项目ID/thumbnails/镜头ID.jpg", "note": "", "tag": ""}],
  "revision": 3,
  "created_at": "ISO时间",
  "updated_at": "ISO时间",
  "analysis": {"method": "transnetv2", "threshold": 0.35, "min_duration": 0.3, "candidate_count": 128, "completed_at": "ISO时间"}
}
```

状态 `ready | processing | error`；进度统一为 `0..1`。新导入 `analysis=null`，提供一个覆盖全长的镜头供原片预览。`analysis.method` 明确记录 `transnetv2` 或主动选择的 `ffmpeg-scene`。自动分镜完整覆盖 `0..duration`，相邻镜头无空隙或重叠；整个视频本身短于最小时长时保留一个镜头。

错误返回 `{error: 中文说明, message: 同一说明}`。常见状态：400 无效输入，404 不存在，409 正在处理/版本冲突/笔记保护，413 超限，415 非 JSON 修改，422 不兼容视频或处理失败，503 缺本地环境。失败会保留已有项目，未完成的上传目录会清理。服务重启后把上次未完成的分析标为 error，可重试。

## 工作台接口

- `GET /api/runtime`：本地处理环境及数据目录。
- `GET /api/projects/{id}/previews`：均匀预览帧缓存。
- `POST /api/projects/{id}/metadata`：`{tags?, source?, removed?, expected_revision}`，检查 metadata_revision。
- `POST /api/projects/{id}/annotation`：`{id?, time, kind, text, expected_revision, delete?}`，kind 为 frame / audio / content，按笔记 revision 检查冲突。
- `POST /api/projects/{id}/asset`：`{kind, id, tags?, note?, deleted?, expected_revision}`，kind 为 captures / audio_clips / exports / music，按 asset_revision 检查冲突。
- `POST /api/projects/{id}/collect`：`{shot_id}`，保存指定镜头的真实画面；重复请求复用已有收藏。
- `POST /api/projects/{id}/save_export`：`{format}`，导出文件落到项目 exports，同时生成收集记录。
- `POST /api/projects/{id}/reveal`：`{kind, id?}`，只在项目内选择允许的文件，用 macOS 访达显示。
- `POST /api/projects/{id}/music`：`{}`，启动真实识曲任务；`music.status` 独立保存 processing / ready / error。
- `GET /api/music`：本地歌曲库。
- `POST /api/music?name=文件名`：音频字节上传；转换 AAC/M4A；返回歌曲库。
- `PATCH /api/music`：`{id, tags?, deleted?, expected_revision}`。
- `POST /api/tags`：`{domain, old, new}`，domain 为 video / image / audio / music；new 留空移除标签，保留素材。

元数据、笔记、素材有独立版本号，不会因为后台进度刷新拒绝正常保存。冲突返回 409。移除为软删除；GET 项目列表排除已移除项目，原文件保留。


## 可搬运资料库

- `GET /api/storage`：当前位置、默认位置、活动任务和最近任务。任务包含 `status`、`message`、`done_bytes`、`total_bytes`、`verified`、`can_release`、`destination`。
- `POST /api/storage/choose-folder {}`：本机 macOS 文件夹选择器；取消返回空路径。其他系统可填写完整路径。
- `POST /api/storage/tasks`：`action=export` + `destination`（父文件夹）+ 可选 `project_id`；省略项目 ID 表示整库。
- 同一任务入口支持 `action=restore` + `source`（项目包目录）、`action=migrate` + `destination`（空目录）、`action=release` + `receipt`（完成导出/迁移的任务 ID）。返回 202 和任务对象；校验失败保留已有资料。
- `POST /api/storage/tasks/:id/cancel {}`：取消任务。最终提交阶段返回 409。
- 文件夹拖放：`POST /api/storage/uploads` 提交清单 → 按清单逐文件 `POST /api/storage/uploads/:id?path=<相对路径>` 上传二进制 → `POST /api/storage/uploads/:id/finish {}` 校验并恢复。取消沿用任务接口；不需先打包压缩。清单上限 64 MiB，文件内容流式写入。

格式 v1：`{format:"lapian-library",version:1,kind:"project"|"library",project_ids:[...],files:[{path,size,sha256}]}`。路径相对于“项目资料/”。拒绝路径越界、符号链接、不完整文件、重复大小写路径和不同版本覆盖。本机项目元数据与包内元数据的比较使用相同的可移植路径转换。

后台任务存在时不开始搬运；搬运期间所有 API 写操作及会生成缓存的读取入口返回 409。状态查询和已有媒体读取保持可用。恢复先在隐藏临时目录校验，再发布完整项目；迁移先复制校验，再原子更新位置配置；释放空间在重新校验目标和本机后才执行。
