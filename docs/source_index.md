# 资料索引

## 本地资料

- `5.【题目五】人形机器人具身智能的长时序任务规划.pdf`
- `第十九届“挑战杯”全国大学生课外学术科技作品竞赛“人工智能+”挑战赛参赛指导手册.pdf`

## 官方开发资料

- 仓库：<https://gitee.com/leju-robot/leju_kuavo_tongverse-challenge-cup-2025>
- 核对分支：`master`
- 核对提交：`5ad3cd7111ea7d6f36e455b92beef0ef3da8de4b`
- 提交时间：2025-07-22T08:13:45Z
- 核对日期：2026-06-07

## 已确认接口

- `env.get_task_params()`
- `env.get_robot_params()`
- `env.reset()`
- `env.step(action) -> (obs, is_done)`
- `TaskSolver(task_params, agent_params)`
- `TaskSolver.next_action(obs) -> action`

任何新增接口必须先在官方资料中确认，并在 PR 中说明来源。

