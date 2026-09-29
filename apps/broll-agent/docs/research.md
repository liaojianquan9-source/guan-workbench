# B-roll Agent 产品与技术核查

核查日期：2026-09-21。记录的是官方能力声明、本机观察与工程判断，三者分别标识。不是对实际模型调用、完整复刻或视觉保真的验收证明；这些由运行记录与验收报告负责。

## 产品边界与同类产品

| 依据 | 已核查事实 | 本产品取舍 |
| --- | --- | --- |
| [Descript Underlord](https://www.descript.com/underlord) | 官方定位是读取脚本、观看视频、建议与执行编辑，支持批量操作。 | Agent必须形成并执行可观察决策，不能只有聊天框。 |
| [Descript Quick design](https://help.descript.com/hc/en-us/articles/44651483515917) | 官方把自动场景与B-roll结果定位为待调节初稿；复杂、多轨、多说话人场景有局限。 | 交付草稿、依据、候选与批量审看，保留用户最终取舍。 |
| [Descript API](https://www.descript.com/api) | 已提供API/MCP，支持导入、提示编辑、transcript/timeline导出；官网媒体直接导出表述不一致。 | 未来可作资产服务消费者；当前不依赖其执行核心渲染。未验证API账号与调用。 |
| [Adobe Media Intelligence](https://helpx.adobe.com/lu_en/premiere-pro/using/media-intelligence-and-search-panel.html) | 官方说明本机分析、结果缓存及sidecar复用；缩小静帧对小细节与快速运动有局限。 | 分离源文件、分析证据和项目；内容相同只保存一次。该官方页搜索可读取，但部分直接打开请求失败。 |
| [Pictory视觉替换帮助](https://kb.pictory.ai/en/articles/10627052-how-to-search-stock-visuals-and-add-them-to-the-video) | 按脚本自动匹配视觉，允许按关键词搜索和逐场景替换。 | 文本匹配是基线；需增加验收后的可复用样式、固定版本引用、证据比较、主动发现缺口。 |

## 三种执行方案

1. **本机Codex模型适配器 + 产品受控工具循环：第一轮选择。** 本机`codex login status`返回已使用ChatGPT登录。CLI支持图片输入、JSONL事件、最终JSON Schema、只读执行、临时会话。无需读取、复制或导出登录凭据。本机应用复用现有登录可先验证闭环；启动与上下文传输有成本，不作为多租户生产服务承诺。
2. **Responses API：保持provider接口兼容。** 自定义工具、视觉输入、结构化输出适合长期服务。调查时常见API key环境变量未设置；未读取密钥内容，也未声称API账号已验证。应由产品保管执行状态和证据，不把模型服务当资产数据库。
3. **纯本地VLM/LLM：暂不作默认。** 当前PATH无Ollama或Whisper CLI；当前python3无MLX、torch、Transformers或Whisper包。只证明已检查环境未发现，不代表整机所有环境都没有。模型下载、设备能力、中文视觉质量尚需单独评测。

官方依据：

- [Codex非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)：自动化管道、JSONL、`--output-schema`、复用登录与只读沙箱；一般自动化建议API key，已有用户账户运行也有官方路径。未读取auth.json。
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)：模型提出工具调用，应用执行并回送结果，然后模型继续。产品需要实现这个循环、参数校验、预算、重试与状态保存。
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)：支持JSON Schema子集；形状合规不能代替证据存在、时长、许可、版本和审批状态的语义校验。
- [视觉限制](https://developers.openai.com/api/docs/guides/images-vision#limitations)：小字、空间位置、计数等可能不可靠；文件名、尺寸和时间码需额外传入。复刻验收同时使用实际渲染和确定性检查。
- [模型目录](https://developers.openai.com/api/docs/models)：官方当前列出GPT-6 Astra及GPT-5.6 Sol/Terra/Luna；最新模型支持文字、图片输入。默认模型应配置化并经本机烟测，不把官方存在误认为账号可用。

## Agent循环与可检验标准

应用持久化run与事件，只记录可审查的决策摘要和工具输入输出，不存隐藏推理。先检查口播、抽帧和历史，再检索候选样式/素材，比较候选并说明弃选原因。证据不足时再次检索或建立缺口；不适合加B-roll的段落必须显式保留人脸。草稿引用固定资产版本。预览后的检查结果回送模型，由模型修订或保留。用户批量决定，修改自动使批准与预览失效。

验证门：实际模型至少完成两轮工具结果反馈；不同口播/素材证据能改变下一步行动；模型失败可恢复且不伪装成离线智能；卡片中的资产、证据和时间码必须存在；终片只用当前批准且通过技术检查的预览。上述是验收标准，不是研究阶段已完成的结果。

## 独立资产服务决定与验证

**依据：** 复刻工程、拉片研究、可用样式、媒体元素及制作项目具有不同生命周期。项目内文件复制无法可靠实现独立跨产品复用。

**取舍：** 资产服务使用Python stdlib、SQLite WAL和SHA256文件存储；不依赖制作应用。数据库保留每个资产的全部不可变revision，修改使用expected_revision防止覆盖并发修改。原文件先复制到内容地址库，之后源文件更改不影响已有引用。通用kind为source/image/audio/style/study/replica；状态、权利、槽位、分析信息属于JSON metadata；制作项目保留在制作应用，引用asset_id+revision。关系记录保存来源与用途，涉及具体版本的关系在metadata中记录revision。

**验证结果：** `python3 -m unittest discover -s apps/broll-agent/tests -p 'test_assets.py' -v` 全部10项通过。覆盖真实临时SQLite、8线程并发CAS唯一成功、内容去重及源文件变化、跨两个HTTP客户端的固定版本复用、关系、HTTP Range、缓存损坏修复、跨站/DNS重绑定阻断，以及完整历史备份恢复和恶意/损坏备份拒绝。测试只使用临时目录，不读写用户资产库。

**协议：** 默认`http://127.0.0.1:4184`；默认数据目录`~/Documents/BrollAssets`。制作应用通过`AssetClient`调用HTTP，不直接打开资产SQLite。`GET /health`；`GET/POST /v1/assets`；`GET/PATCH /v1/assets/{id}`；`GET /v1/assets/{id}/revisions/{n}`；`POST /v1/blobs`（原始bytes）；`GET /v1/blobs/{sha}`（Range）；`GET/POST /v1/relations`。扩展`GET /v1/export`下载ZIP，`POST /v1/restore`上传ZIP恢复。HTTP错误为JSON；404对应不存在、409对应版本冲突。

**使用：** `python3 asset_server.py`启动；可用`--root`和`--port`覆盖。另一个产品通过`AssetClient(base_url)`或上述HTTP协议即可接入。文件上传由调用产品读取后发送bytes，服务不接受外部请求指定服务器任意文件路径。启动不扫描磁盘、不自动导入媒体。资产服务默认只监听loopback；跨机器部署、用户鉴权及权限模型尚未实现，不能直接暴露到公网。

## 许可与来源

- [Remotion当前许可证](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)：个人、最多3名员工的营利组织、非营利及非商业评估可用免费许可；其他实体需公司许可。禁止出售或再许可Remotion本身的衍生版本。[5.0变更](https://github.com/remotion-dev/remotion/pull/3750)在本次查阅仍显示draft；按实际锁定版本复核，不将其当已生效。
- [FFmpeg官方许可](https://ffmpeg.org/legal.html)：基础LGPL，启用GPL部件会改变适用许可。当前使用本机已安装命令；将来打包分发应核查实际构建，不宣称任意构建均可自由重新分发。
- [Pexels许可](https://www.pexels.com/license/)：允许使用与修改，不允许作为另一个素材平台再分发或售卖。可进成片不等于可公开分发原素材。

资产metadata应持续保存来源、许可、署名要求、使用范围、可否再分发及权利核查状态。库中参考片的权利尚未由此研究确认；拉片证据、重建代码和参考原素材必须分别记录。入库、技术验收或样式发布不会自动改变来源权利。
