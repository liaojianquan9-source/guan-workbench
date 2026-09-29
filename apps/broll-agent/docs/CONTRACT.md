# B-roll Agent · 第一轮接口合同

2026-09-21。此合同由主 Agent 维护。已有工作台、案例、原片保持原样。

## 产品选择

目标是从参考研究到可复用样式，再到有证据的口播草稿和实际成片。保留已有拉片工具，新增独立资产服务与制作应用。

比较过三种方案：继续扩展旧 project.json 最快，但无法独立共享资产和保存草稿；整体重写会浪费已验证的本地媒体能力；独立资产服务 + 新 Agent 制作域 + 旧工具适配，边界清楚且可逐段验收，因此选择第三种。

## 文件边界

- asset agent: `asset_store.py`, `asset_server.py`, `asset_client.py`, `tests/test_assets.py`, `docs/research.md`。
- render agent: `renderer.py`, `replica.py`, `renderer/`, `tests/test_rendering.py`, `docs/rendering.md`。
- UI agent: `public/`, `tests/test_ui.cjs`。其他文件只读。
- 主 Agent: 模型/provider、Agent循环、制作项目、HTTP应用、启动/验证/真实验收、集成和决策记录。
- 每位 agent 仅暂存自己的文件并在测试通过后提交；不使用 git add .。接口变化先通知主 Agent。

## 独立资产服务

Python stdlib。默认 127.0.0.1:4184，独立 data root；SQLite WAL + SHA256 blobs。App 使用 HTTP AssetClient，不直接访问资产数据库。可由任意其他产品使用相同 API。

`AssetStore(root)` 与 `AssetClient(base_url)` 提供相同业务方法（远端 blob_path 由 client 下载到缓存实现）：

```
put_blob(path, media_type=None) -> {sha256,size,media_type}
blob_path(sha256) -> Path
create_asset(kind,name,metadata=None,blob_hash=None,asset_id=None) -> asset
get_asset(id,revision=None) -> asset
revise_asset(id,expected_revision,patch) -> asset
list_assets(kind=None,query=None,status=None) -> list[asset]
add_relation(subject_id,object_id,predicate,metadata=None) -> relation
relations(asset_id) -> list[relation]
export_bundle(destination) -> manifest
restore_bundle(source) -> result
```

asset = `{id,revision,kind,name,metadata,blob_hash,created_at,updated_at}`。kind: source/image/audio/style/study/replica。metadata 为 JSON，不把产品专有字段加入通用资产schema。revision 不可变；patch可含 name/metadata/blob_hash，metadata整体替换。历史引用必须固定 id+revision。错误用 ValueError/KeyError，冲突为 ValueError。

HTTP: GET/POST `/v1/assets`; GET/PATCH `/v1/assets/{id}`; GET `/v1/assets/{id}/revisions/{revision}`; GET/POST `/v1/relations`; POST `/v1/blobs` raw bytes, GET `/v1/blobs/{sha}`（Range）；GET `/health`。外部产品通过这些协议接入；host/origin校验阻止浏览器跨站写。

## 渲染与复刻

`Renderer(asset_client, work_root)`：

```
render(style_asset, fields, output_dir, *, duration=None) -> {video: str,poster: str,report: dict}
compose(source_path, approved_cards, output_path) -> {video: str,report: dict}
```

render 输出绝对路径；actual fields 必须进入 Remotion props。style.metadata 含 renderer_id、field_schema（每字段 label/type/default/max_length）、duration、用途/不适用情形、source evidence、fidelity_status、technical_status、包版本/来源。适配器只执行内置审查过的 renderer_id；任意上传脚本不可执行。图片字段引用资产 `{asset_id,revision}`，由 renderer 下载固定版本。本次至少移植两个真实现有样式，覆盖换字、换图；不得改原案例。

compose 输入 card `{id,start,end,render_path}`，只接受已经批准的项目快照；音频沿用口播，B-roll覆盖指定范围，时长不变。输出probe报告需检查时长/画幅/音轨。

`ReplicaService(asset_client, renderer, work_root)`：

```
available_cases() -> list[dict]
import_case(case_id) -> {replica: asset, styles: list[asset]}
study(source_asset,start,end,note='') -> asset
```

研究记录保存源哈希/范围/抽帧/笔记；复刻项目保存Skill阶段证据；style发布与自动保真分开。import_case只导入已知审查过的案例，机器可用性通过真实渲染+替换检查后才可用，保真待审如实保存。后续任意片段进入复刻任务，不能假装已自动复刻。

## 制作应用 HTTP（4183）

所有返回JSON（除媒体），错误 `{error}`；列表包装对象。 

- GET `/api/status` -> `{model,assets,capabilities}`
- GET `/api/assets?kind=style|image|source|study|replica` -> `{assets}`
- POST `/api/upload?kind=image|source&name=…` raw bytes -> `{asset}`
- GET `/api/media/{sha}` -> bytes
- GET `/api/cases` -> `{cases}`；POST `/api/cases/import` `{case_id}` -> `{replica,styles}`
- POST `/api/studies` `{source_id,start,end,note}` -> `{study}`
- GET `/api/workbench-projects` -> `{projects}`；POST `/api/workbench-import` `{project_id}` -> `{project}`（真实字幕/原片）
- GET `/api/projects` -> `{projects}`；POST `/api/projects` `{name,source_id?,transcript?,segments?}` -> `{project}`
- GET `/api/projects/{id}` -> `{project}`
- POST `/api/projects/{id}/run` `{}` -> `{run}`（异步）；GET `/api/runs/{id}` -> `{run}`
- POST `/api/projects/{id}/batch` `{revision,card_ids,action:'approve'|'reject'|'reset'|'replace',fields?,style_id?}` -> `{project}`
- POST `/api/projects/{id}/preview` `{card_ids}` -> `{job}`；POST `/api/projects/{id}/render` `{}` -> `{job}`；GET `/api/jobs/{id}` -> `{job}`
- GET `/api/files/{project_id}/{filename}` -> preview/final media only
- GET `/api/projects/{id}/export` -> portable project JSON with fixed asset references

project `{id,name,revision,source:{asset_id,revision}|null,segments:[{id,start,end,text}],cards:[],runs:[],created_at,updated_at}`。
card `{id,segment_ids,start,end,text,decision:'broll'|'keep'|'gap',reason,evidence:[],alternatives:[],style:{asset_id,revision}|null,fields:{},missing:[],status:'draft'|'approved'|'rejected',preview_url?,render_report?}`。
run `{id,project_id,status,events:[{sequence,type,message,data,time}],error?}`。Event只记录可检查的决策摘要和工具输入输出，不保存隐藏思维链。

## 检查点

Agent 负责读取字幕/抽帧/历史、检索样式和素材、比较、生成草稿、检查并修订。任何保留口播/缺素材决定都必须可见。模型失败保留状态并允许重试，不冒充离线智能。修改卡片使批准与预览失效。最终合成只使用当前已批准且经技术检查的版本；未批准内容保留原口播。原始素材权利不因入库自动改变，来源和许可始终随资产保存。

真实验收必须覆盖：同一资产跨两个项目固定版本复用、模型实际调用多步工具、批量替换与批准、真实Remotion重渲染、口播合成以及负面路径。测试数据批准记录标明 test/reviewer，不冒称用户批准。
