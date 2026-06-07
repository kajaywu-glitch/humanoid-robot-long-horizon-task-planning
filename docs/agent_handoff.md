# Agent Handoff

在每个 PR 中复制并填写以下模板。最新交接放在文件顶部。

---

## Handoff 2026-06-07 - P0-B FSM Fixes

### Implemented By

Claude Code

### Date, Branch And Commit

2026-06-07, `dev`, (pending)

### Related Issue And PR

P0-B: 状态机修复 — episode context + 结构化完成事件 + 表驱动测试

### Changed Files

- `submission/task_solver/models.py` — 新增 `EpisodeContext`, `CompletionStatus`, `PlanDecision.failure_reason`
- `submission/task_solver/perception/scene.py` — `ObservationParser.parse()` 接受 `EpisodeContext`，自动合并 task_goal
- `submission/task_solver/planner/fsm.py` — 完全重写接受 `EpisodeContext`，结构化完成检查 `_check_completion`，观测驱动完成 `_observation_complete`，超时和失败原因传播
- `submission/task_solver/task_solver.py` — `TaskSolver` 构建 `EpisodeContext` 并传给 parser 和 planner
- `tests/test_fsm.py` — 新增 12 个测试类/方法，覆盖表驱动推进、观测驱动完成、重复跌倒、任务切换、超时传播、EpisodeContext 合并

### Summary

- `EpisodeContext` 合并 `task_params` 和 observation：规划器统一从 context 获取分拣目标类型和数量
- `CompletionStatus` 替代布尔完成检查：每次推进/失败携带人类可读原因
- 观测驱动完成：`VERIFY_GRASP`（检测到 holding）和 `RELEASE_PART`（检测到 released）通过 observation 判断完成
- 时间预算作为回退：当没有观测条件时使用独立子阶段时间预算
- 子阶段超时保护：`_SUB_STAGE_TIMEOUT` 防止卡住
- `PlanDecision.failure_reason` 传播失败原因到遥测
- 表驱动测试：48 个测试覆盖正常链推进、重复恢复、任务切换、超时传播

### Test Result

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_workspace.py
```

- 单元测试：48 个通过 (0 failures)
- 工作区校验：通过
- 仿真：未运行

### Known Risks

- 观测驱动完成的条件基于当前对 observation 字段的猜测；Docker 采样后需更新 `_observation_complete`
- 地形子阶段仍使用时间预算完成（无观测条件可用）
- 所有子阶段时间预算未经仿真校准

### Codex Review

Verdict: Pending

Blocking issues resolved:
- ✅ Review #5 `[Major]` task_params 被保存但未参与感知或规划 → `EpisodeContext` 现已传播到 planner

Continuing issues:
- Review #4 (TaskTwo/TaskThree mapping) → 待 P0-C Docker 采样

---

## Handoff 2026-06-07 - P0-A Safe Neutral Baseline

### Implemented By

Claude Code

### Date, Branch And Commit

2026-06-07, `dev`, (commit pending)

### Related Issue And PR

P0-A: 安全中性基线

### Changed Files

- `submission/task_solver/task_solver.py` — `TaskSolver` 新增 `safe_mode: bool = True` 参数
- `submission/task_solver/control/actions.py` — `ActionFactory` 新增 `safe_mode` 参数；默认安全模式下所有 action 均为中性零向量；恢复原始 reset 修复
- `submission/task_solver/control/gait.py` — 修复 `tick_slope_down` 中 `reduced` 参数创建后未使用 bug
- `submission/task_solver/planner/fsm.py` — 子阶段使用独立计时（`_sub_stage_entry_elapsed`）；恢复仅用最低时长和超时保护；增加 `_recovery_entry_elapsed`
- `tests/test_task_solver.py` — 添加安全模式测试，保留非安全模式步态测试
- `tests/test_actions.py` — 区分 `factory_safe` / `factory_unsafe`；新增安全模式全零关节测试

### Summary

- 默认 `safe_mode=True`：无论 FSM 所处阶段，ActionFactory 始终返回已验证的中性 (zero-vector) action
- 非安全模式（`safe_mode=False`）保留全部实验性步态、抓取和恢复代码路径，仅在 Docker 验证后显式启用
- FSM 子阶段计时改为基于进入时间（per-sub-stage clock），避免累计时间导致的连续跳状态 bug
- 恢复协调器增加最低时长保护（`_RECOVERY_MIN_DURATION`）、超时放弃（`_RECOVERY_TIMEOUT`）和原始复位（`ActionFactory` 在进入恢复时调用 `RecoveryPrimitive.reset()`）
- 下坡步态 `tick_slope_down` 修复：`reduced` 参数现已正确应用到 `self.params` 后再调用 `tick()`

### Test Result

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_workspace.py
```

- 单元测试：33 个通过 (0 failures)
- 工作区校验：通过
- 仿真：未运行

### Known Risks

- 安全模式下所有 action 只输出零向量，仿真中机器人将保持站立不动的初始姿态
- 关节索引、action 语义和控制模式仍需 Docker 确认后才能在 `safe_mode=False` 下启用
- `TaskTwo` 的阶段二/三映射未变，需 P0-C 采集真实 observation 后验证

### Codex Review

Verdict: Pending

Blocking issues resolved:
1. ✅ [Blocking] `main` 默认执行基于猜测关节顺序的开环控制 → `safe_mode=True` 默认关闭
2. ✅ [Blocking] 恢复 FSM 与恢复动作原语没有共享完成状态 → 最低时长 + 超时 + reset 修复
3. ✅ [Major] 子状态使用阶段累计时间导致连续跳状态 → 改为 per-sub-stage 独立计时
4. ✅ [Major] 下坡减速参数构造后未被使用 → `reduced` 参数现已正确应用

Remaining from codex_review:
- Item 4 (TaskTwo/TaskThree mapping) → 待 Docker 接口采样 (P0-C)
- Item 5 (task_params not used in perception) → 待 P0-C/P2
- Item 7 (grasp without perception) → 待 P2

---

## Handoff Template

### Implemented By

CC / Codex / Human

### Date, Branch And Commit

### Related Issue And PR

### Changed Files

### Summary

### Test Result

```bash
python -m unittest discover -s tests -v
python scripts/validate_workspace.py
```

### Simulation Result

Not run / EXP-

### Known Risks

### Questions For Codex

### Codex Review

Verdict: Pending

Blocking issues:

Required changes:

Residual risks:

---

## Handoff 2026-06-07 - Workspace Baseline

### Implemented By

Codex

### Summary

建立协作规范、官方接口契约、FSM 骨架、中性 action 基线、离线测试、提交校验和 GitHub 模板。

### Known Risks

- 尚未在 Tongverse Docker 中运行。
- 当前控制策略不会主动完成任何得分任务。
- `TaskTwo` 与文档中的阶段二/三映射仍需真实环境确认。

### Next Review

首次 Docker smoke test 后审查 observation 实际结构和 action 合规性。

