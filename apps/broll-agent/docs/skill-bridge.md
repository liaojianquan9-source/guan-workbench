# 复刻 Skill 执行桥

2026-09-21。此模块补足“保存研究后，只剩一条需要人工跑 Skill 的说明”的断点。它把已安装 Skills 的实际工具放进可观察、可恢复的产品任务。生成的新源码始终是待审候选，不会自动进入制作应用的受信任 renderer 白名单。

## 接口与集成

```python
from skill_runner import SkillRunner

runner = SkillRunner(asset_client, work_root / "skill-cases")
replica = runner.create(study_asset)
replica = runner.advance(replica["id"], "preflight")
replica = runner.advance(replica["id"], "auto")
```

`create(study_asset)`接受已保存研究，要求source资产及其revision、原文件SHA256、start/end完整。已有`ReplicaService.study()`建立的`metadata.replica`会被接管，保留同一个项目。新建项目会把关联写回研究资产。返回kind为replica的共享资产。

`advance(replica_id, stage='auto')`执行一块工作并返回新的资产revision，适合由应用异步job调用；不要放在浏览器同步短超时请求中。可选stage为preflight/layout/motion/implementation/qa/validate/auto。

- 新案例第一次auto或preflight真实运行安装目录中的`inspect-clip.py`，再运行`validate-case.mjs`，这次调用在预检后结束。
- 已有案例恢复先读合同、运行校验、核对固定来源与范围，避免重新裁片覆盖证据。
- auto在首个可推进阶段让只读Codex Agent主动读case/来源/抽帧，选择generate或wait并给证据路径和理由。证据不足或已需审阅时可等待。
- generate调用Codex执行已授权单阶段工作，显式读取4个Skill和相应引用。模型按证据选择工具、比较处理方案、生成产物、运行校验并修正。产品再独立运行validate-case，校验必需产物，保存结果。
- 存在needs_review时auto不会自动批准。明确调用当前未完成stage可重试/修复该阶段；跨越上游门会被拒绝。validate只核对当前状态。

此桥没有“发布”方法。布局需要视觉审阅，后续阶段遵守Skill前置门。当前产品的受信任样式仍只能由审查过的适配器提供；任意新参考片完整自动高保真复刻尚未验收。

## 状态、证据与恢复

共享资产metadata保存固定study/source引用、来源SHA256、范围、阶段、technical_status、fidelity_status与`skill_bridge`。后者包含4个Skill的版本内容哈希、运行次数、阶段决策、证据blob、文件哈希清单、候选包哈希与当前工作目录。

每轮工具的命令、退出码、耗时、超时、公开工具输出及模型结论保存为JSON blob。模型JSONL中只保留公开命令/文件变更/消息及完成事件，丢弃reasoning事件。可恢复ZIP保存case.json、evidence、specs、remotion与validation；node_modules和.git不入包。包以不可变blob跟随每个replica revision保存，另一个产品或工作目录可下载恢复后校验。

预检源片与evidence/source.json受保护；模型若改变来源、范围或已通过布局证据，桥恢复原文件并记录失败。机器校验成功仅证明合同与文件，不代表静帧、运动或视觉通过。生成后阶段强制needs_review，`execution_trust=untrusted_candidate`、`trusted_renderer=false`、`human_review=pending`始终明确。

模型失败、超时、返回无效结果或缺产物时保存部分成果与失败日志，允许重试。进程超时终止整个进程组，包含子渲染进程；同一项目用文件锁防止并发覆盖。预检中断留下半成品时先归档旧尝试，再在新目录重跑，绝不使用`--force`覆写旧状态。工作目录丢失可从共享ZIP恢复。

## 执行边界

只调用已安装总控`inspect-clip.py`和`validate-case.mjs`作为产品受控机械工具；它们的写入目标均为新工作case。不会自动执行setup脚本、更新Skill或原案例。生成Agent使用`--ignore-user-config --ephemeral`，认证仍由Codex自身处理，产品不读取auth.json。模型通过`model`参数或`BROLL_MODEL`配置，默认与制作Agent一致为gpt-6-astra；CLI路径可用`BROLL_CODEX`覆盖。先在case创建独立Git根，再以case为工作根开启workspace-write，禁用shell网络、web search、Apps及电脑/浏览器操作和额外临时目录写入；不把应用仓库根作为生成工作域。宿主写入的模型最终结果放在case外的专用控制目录，候选符号链接会被移除，避免生成代码重定向宿主写入。

Python/Node/FFmpeg或Skill运行时缺失会记录失败，不悄悄安装。新代码可能在隔离case中由生成Agent作候选探针，但不会被产品渲染服务当作受信任组件运行。源码、技能文字和渲染结果各自保留验证边界。

## 本轮验证

`python3 -m unittest discover -s apps/broll-agent/tests -p 'test_skill_runner.py' -v`：11项通过。测试真实调用已安装inspect与validate；覆盖接管已有replica、固定源预检、另一工作根恢复、错误阶段拒绝、模型失败后重试、Agent选择等待、保护源文件、禁止自报passed、进程树超时、隐藏reasoning不入记录、Codex作用域参数与4个Skill入口、预检中断恢复、生成符号链接不能重定向宿主证据写入。模型行为测试使用可控替身，不据此声称真实生成已验收。

真实素材烟测另外使用仓库`inputs/kimi-k3-000-011-reference.mp4`，通过独立HTTP资产服务及AssetClient运行：

- 源SHA256：`7be08311f422f0e5fd7ce415d6c8577051692f497b07c62b32b500c244bc9271`，执行前后相同。
- 选择0.2–0.6秒；实际解码12帧、30fps；inspect-clip及validate-case退出码均0。
- preflight=passed，其余4阶段pending；fidelity仍needs_review，无新style发布。
- 预检证据SHA256：`a32554c301c6ca12b8f426c4af64b5aa92a6511be4e82528685879d6eb79d6da`。
- 案例包SHA256：`7772e3ac5b716ff7077d289eaf614934790c95827b1a51ad0ddd286f3e6f2257`。
- 在新的工作根从包恢复，独立validate-case再次通过；恢复证据SHA256：`53b31d67cb8e7338888dd7599043e01ea81ab8bf607dae0c69d6660d1387e86d`。

该技术烟测使用隔离临时库；主产品真实验收应另存自己的项目/证据。尚未在本轮运行真实模型生成完整新场景，未宣称通用复刻、运动保真或新源码正式渲染通过。
