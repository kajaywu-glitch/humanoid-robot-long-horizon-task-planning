# 人形机器人具身智能的长时序任务规划

本仓库是 Tongverse 挑战赛题目五的协同研发工作区。当前目标不是直接追求完整控制策略，而是先建立可追踪、可测试、可复现、可打包的工程基线。

## 当前状态

- 已整理赛题目标、评分规则、提交约束和官方接口。
- 已建立 `Owner -> Issue -> CC -> PR/Handoff -> Codex Review -> Simulation -> Merge` 协作闭环。
- 已建立 `TaskSolver`、长时序 FSM、观测解析和合法 action 构造的离线基线。
- 当前策略默认为安全中性模式 (`safe_mode=True`)，仅输出已验证的零向量动作；实验性步态、抓取和恢复控制在 `safe_mode=False` 下可用，但必须在 Tongverse Docker 环境内逐阶段验证关节索引、控制模式和 observation 字段后方可启用。

## 目录

```text
submission/task_solver/  最终算法实现，生产代码只在这里扩展
tests/                   不依赖 Tongverse 的单元与契约测试
docs/                    需求、架构、决策、交接、实验和提交文档
experiments/             结构化实验结果
scripts/                 本地验证与提交包生成工具
.github/                 Issue、PR 和 CI 协作模板
```

`submission/task_launcher.py` 来自官方仓库，禁止修改。官方要求最终实现集中在 `submission/task_solver/`。

## 快速检查

Windows:

```powershell
python -m unittest discover -s tests -v
python scripts/validate_workspace.py
python scripts/prepare_submission.py
```

Linux / Tongverse Docker:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_workspace.py
python3 submission/task_launcher.py
```

官方运行环境要求 Ubuntu 20.04、Docker、NVIDIA Container Toolkit 和高性能 NVIDIA GPU。当前 Windows 主机未检测到 Docker，因此真实仿真验证尚未执行。

## 开始协作

1. 阅读 `AGENTS.md`、`docs/problem_understanding.md` 和 `docs/decision_log.md`。
2. 从 Issue 建立 `feat/*` 或 `fix/*` 分支。
3. 只实现 Issue 约定的最小闭环，并补测试。
4. 更新 `docs/agent_handoff.md`；真实仿真后更新 `docs/experiment_log.md` 和 `experiments/results.csv`。
5. 核心规划、控制、阻塞故障和合并到 `main` 前必须经过 Codex 审查。

## 上游基线

- 官方仓库：<https://gitee.com/leju-robot/leju_kuavo_tongverse-challenge-cup-2025>
- 本工作区核对提交：`5ad3cd7111ea7d6f36e455b92beef0ef3da8de4b`
- 核对日期：2026-06-07

