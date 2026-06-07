# AGENTS.md

## Project Goal

在 Tongverse 仿真环境中构建可复现的长时序任务规划系统，依次完成：

1. 通过上楼梯、下坡和不平路段。
2. 识别任务指定的 A/B/C 零件，并将 3 个正确零件放入收纳箱。
3. 搬起收纳箱，放到对应颜色货架中层，并稳定保持 10 秒。

## Source Of Truth

- GitHub Issue 定义任务、范围和验收标准。
- Pull Request 承载代码变更、测试结果和风险。
- `docs/decision_log.md` 记录不可随意推翻的技术决策。
- `docs/agent_handoff.md` 记录 CC 与 Codex 的异步交接。
- `docs/codex_review.md` 记录 Codex 的持续审阅结论、问题和改进方向。
- `docs/experiment_log.md` 和 `experiments/results.csv` 记录绑定 commit 的仿真事实。

聊天记录不是项目事实源。

## Hard Rules

- 只能通过官方 `Env` 交付的 observation 和 action 接口工作。
- 不直接调用未批准的仿真内部函数。
- 不硬编码完整动作轨迹；参数化动作原语必须有感知反馈、超时和失败处理。
- 不修改官方 `submission/task_launcher.py`。
- 最终生产代码只放在 `submission/task_solver/`。
- 每次决策、状态切换、重试和失败都必须可记录。
- 每次实验必须记录 commit、seed、命令、得分、耗时和产物。
- `main` 始终代表可运行的提交候选。

## Roles

- Owner：确定路线、优先级、验收标准、接口边界、合并和版本冻结。
- CC：每次工作前先阅读 `docs/codex_review.md` 的最新记录，再按 Issue 实现功能、测试、文档、运行脚本和普通修复。
- Codex：架构审查、核心规划/控制审查、阻塞故障、重构和提交前审计。

## Branches

- `main`：稳定提交候选。
- `dev`：集成分支。
- `feat/*`：功能。
- `fix/*`：缺陷。
- `docs/*`：文档。
- `exp/*`：实验性策略。

## Pull Request Requirements

每个 PR 必须说明：

1. 改了什么以及为什么。
2. 关联 Issue。
3. 测试和仿真命令。
4. 结果、commit 和 seed。
5. 已知风险与回滚方式。
6. 是否需要 Codex 审查。

## Codex Escalation

以下情况必须升级给 Codex：

- 修改规划器或控制接口的核心架构。
- 同一阻塞问题由 CC 修复两次仍失败。
- 变更跨越 3 个以上核心模块。
- 可能违反官方接口或提交规则。
- 准备合并到 `main` 或生成提交候选。

## Definition Of Done

- 验收标准全部满足。
- 单元测试和工作区验证通过。
- 关键日志能够解释行为。
- 若已接仿真，实验记录包含 commit、seed、得分和失败原因。
- 文档与实际命令一致。
