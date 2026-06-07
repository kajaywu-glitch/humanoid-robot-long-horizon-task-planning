# Decision Log

## D001 - 先使用有限状态机

Date: 2026-06-07  
Status: Accepted

首版使用 FSM，而不是行为树或 LLM 在线规划。原因是阶段评分清晰、便于 Mock 测试、超时和失败可追踪。稳定基线后再评估行为树。

## D002 - 生产代码遵守官方提交边界

Date: 2026-06-07  
Status: Accepted

所有最终算法代码放在 `submission/task_solver/`。研发文档、测试和工具可位于仓库其他目录，但不得要求修改官方 launcher。

## D003 - 离线基线零外部依赖

Date: 2026-06-07  
Status: Accepted

首版只使用 Python 标准库，action 使用官方接受的 List。视觉或数值依赖必须通过独立 Issue 引入，并记录 Docker 安装与版本。

## D004 - GitHub 是唯一事实源

Date: 2026-06-07  
Status: Accepted

任务进入 Issue，代码进入 PR，关键决策进入本文件，Agent 交接进入 handoff，仿真事实进入 experiment log，并绑定 commit。

## D005 - 分数优先于一次性完整方案

Date: 2026-06-07  
Status: Accepted

按 10 分地形、单个零件、搬箱保底等可验证里程碑推进。每个阶段都允许独立形成可回滚 baseline。

