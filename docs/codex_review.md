# Codex Review Log

本文件是 Codex 对项目进行持续审阅的固定记录。CC 每次开始实现、修复或提交
PR 前必须先阅读最新一条记录，并在交接中说明已处理项和未处理项。

## 使用规则

- 最新审阅记录放在最上方。
- 每条记录必须包含日期、审阅范围、结论、存在问题和下一步改进方向。
- 问题分为 `Blocking`、`Major` 和 `Minor`。
- 未解决的 `Blocking` 问题不得合并到 `main` 或生成提交候选。
- CC 完成修改后，在 `docs/agent_handoff.md` 中列出对应问题及验证结果。
- 真实仿真结论仍须写入 `docs/experiment_log.md` 和
  `experiments/results.csv`，本文件不能替代实验记录。

## 审阅模板

### Review YYYY-MM-DD - Title

**审阅范围**

- 分支：
- Commit：
- 关联 Issue / PR：
- 文件或模块：

**结论**

Verdict: `Approved` / `Changes Required` / `Blocked`

**存在问题**

1. `[Blocking|Major|Minor]` 问题描述。
   - 证据：
   - 风险：
   - 要求：

**下一步改进方向**

1. 可执行的改进项及验收方式。

**验证结果**

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_workspace.py
```

- 单元测试：
- 工作区校验：
- 仿真：

---

## Review 2026-06-07 - Initial Workspace Audit

**审阅范围**

- 分支：`main`
- Commit：无，仓库尚未建立首个 commit
- 关联 Issue / PR：无
- 文件或模块：项目文档、FSM、感知解析、动作构造、步态、遥测和测试

**结论**

Verdict: `Changes Required`

离线工程结构和接口契约测试已经建立，但当前代码不能作为 Tongverse 可运行或
可得分基线。真实 observation、robot params 和 action 行为均未经过 Docker
仿真确认。

**存在问题**

1. `[Blocking]` `main` 尚无 commit，所有项目文件均为未跟踪状态。
   - 证据：`git status` 显示 `No commits yet on main`。
   - 风险：实验无法绑定 commit，无法形成可回滚候选版本。
   - 要求：由 Owner 确认当前基线内容，建立首个可追踪 commit。

2. `[Blocking]` 控制层使用未经官方参数确认的关节索引和开环动作。
   - 证据：`control/gait.py` 明确标注关节索引为猜测值；地形、操作和恢复动作
     已由 `control/actions.py` 实际输出。
   - 风险：可能输出错误关节命令、导致摔倒，或违反参数化动作原语必须具备
     感知反馈和失败处理的项目规则。
   - 要求：在获得真实 `agent_params` 和 observation 样本前，不得将这些动作
     视为安全生产策略；Docker smoke test 后重新审查控制映射。

3. `[Major]` FSM 主要依赖阶段累计时间推进，而非阶段完成反馈。
   - 证据：`planner/fsm.py` 中 `_sub_stage_complete` 使用固定分钟预算。
   - 风险：状态可能在动作未完成时提前推进，且多个子状态共享阶段累计时间，
     无法表达单个动作的真实超时。
   - 要求：为每个子状态记录进入时间，并使用 observation 中可验证的完成条件；
     时间只作为超时和失败保护。

4. `[Major]` 文档与代码行为不一致。
   - 证据：`README.md` 声明当前策略仅输出中性动作，代码和测试则要求地形阶段
     输出非零正弦步态。
   - 风险：Owner、CC 和审阅者可能基于错误基线做决策。
   - 要求：确定是回退到中性安全基线，还是将步态移至实验分支；随后同步 README、
     架构和交接记录。

5. `[Major]` manipulation 流程尚无目标识别、抓取点或抓取成功闭环。
   - 证据：抓取阶段固定发送 `right_hand`，手臂姿态为固定关节目标；
     `record_successful_grasp` 未与 observation 反馈连接。
   - 风险：无法确认目标类别，可能误抓并被扣分。
   - 要求：真实字段确认后，先实现低置信度拒抓和单个正确零件闭环。

6. `[Minor]` 离线测试主要验证数组尺寸和数值变化，未验证官方控制语义。
   - 证据：当前 34 个测试全部通过，但未加载真实 robot params 或 observation。
   - 风险：测试通过可能被误解为仿真兼容。
   - 要求：加入脱敏的真实契约 fixture，并区分离线契约测试和仿真测试。

**下一步改进方向**

1. 建立首个基线 commit，保证后续实验、交接和回滚可追踪。
2. 在官方 Ubuntu 20.04 Tongverse Docker 中运行最小 smoke test。
3. 记录 `task_params`、`agent_params` 和各阶段 observation 样本。
4. 核对 action 控制模式、关节顺序、单位、频率和 `pick` 语义。
5. 基于真实反馈重构 FSM：感知条件负责完成判定，子状态计时负责超时。
6. 完成上述信息采集前，禁止将猜测步态直接作为 `main` 的提交候选策略。

**验证结果**

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_workspace.py
```

- 单元测试：34 个通过
- 工作区校验：通过
- 仿真：未运行

