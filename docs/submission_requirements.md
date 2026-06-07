# 提交要求

## 赛题文件中的原始要求

- 材料说明文档：设计方案、测试报告、总结报告、使用说明等。
- 算法模块：源代码、任务执行脚本、仿真部署说明。
- 程序需要能够在 Docker 仿真环境中运行。
- 只能调用仿真环境提供的指定函数接口。
- 未自行修改控制器时，需要提交覆盖全部任务的脚本。
- 若自行修改控制器，还需提交控制器、可编译控制器的 Docker 镜像、安装说明和其他必要文档。

赛题文件列出的截止时间是北京时间 2025-08-17 24:00；截至本工作区建立日期 2026-06-07，该日期已经过去。若这是复赛、复现或后续活动，应由 Owner 重新确认当前有效的提交窗口和渠道。

## 官方仓库约束

- 仅在 `submission/task_solver/` 内实现算法。
- 不修改 `submission/task_launcher.py` 或其他核心文件。
- `TaskSolver.__init__` 接收 `task_params` 和 `agent_params`。
- `TaskSolver.next_action(obs)` 返回规定 action。
- 额外 Python 包应追加到官方 `docker-pip-install.sh` 并在每次启动容器后安装。
- 测试命令为 `python submission/task_launcher.py`；阶段一失败后，按官方说明续跑阶段二。

## 上游待确认项

核对的官方 `master` 提交 `5ad3cd7` 中，`submission/task_launcher.py` 仍包含交互式 `pdb.set_trace()`，且命令行判断使用 `len(sys.argv) < 5`。这会影响无人值守运行，但官方同时禁止参赛者修改 launcher。当前工作区保持该文件字节级一致，并将此问题列为必须向官方确认的 P0 项。

## 提交前检查

- [ ] 从干净环境解压后能按 README 启动
- [ ] launcher 与官方版本一致
- [ ] 所有实现位于 `submission/task_solver/`
- [ ] 未导入或调用未批准的仿真内部 API
- [ ] action 数组长度与机器人参数一致
- [ ] 运行脚本覆盖所有任务
- [ ] 随机 seed、日志和超时行为可复现
- [ ] 至少完成 3 个不同 seed 的完整回归
- [ ] 文档、代码、模型和配置均进入提交包
- [ ] 删除断点、临时文件、大型无用产物和敏感信息
