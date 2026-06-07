## Summary

## Related Issue

Closes #

## Implementation Notes

## Test Commands

```bash
python -m unittest discover -s tests -v
python scripts/validate_workspace.py
```

## Simulation Result

Not run / EXP-

## Known Risks And Rollback

## Checklist

- [ ] 未修改 `submission/task_launcher.py`
- [ ] 未调用未批准的仿真接口
- [ ] 未硬编码完整动作轨迹
- [ ] 状态切换、超时和失败原因可追踪
- [ ] 已添加或更新测试
- [ ] 已更新 handoff 和必要文档
- [ ] 仿真结果绑定 commit 和 seed

## Codex Review

- [ ] Not needed
- [ ] Needed before merge to `dev`
- [ ] Needed before merge to `main`

