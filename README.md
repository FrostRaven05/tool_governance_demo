# 第二章作业：新增转账工具

## 文件

- `tool_governance_demo.py`：附录治理框架及转账工具实现。
- `tests/test_tool_governance.py`：五项转账测试，所有业务调用经过 `runtime.invoke()`。
- `requirements.txt`：本次验证使用的依赖版本。
- `验收记录.md`、`验收输出.txt`：打包时重新执行的验收结果。

## 安装与运行

需要 Python 3.11 或以上；本次使用 Python 3.12。解压后进入含本 README 的目录：

```bash
python -m pip install -r requirements.txt
python -m pytest tests/test_tool_governance.py -v -k "transfer"
```

查看审批状态和审计中的脱敏账号：

```bash
python -m pytest tests/test_tool_governance.py -v -s -k "transfer_approval_binding"
```

预期包含 `Before approval: CONFIRM (APPROVAL_REQUIRED)` 和 `ACC-A-****3456->ACC-A-****8888`。

```bash
python tool_governance_demo.py
```

上述默认离线演示保留原附录的订单/退款/Shell 场景；转账完整演示在审批绑定测试中完成。所有账户与转账均为内存模拟，不需要 API Key。附录保留的 `--agent` 模式需要另外安装 openai 并配置密钥，不属于本次作业验收。

## 实现内容

1. 四个按租户和账号索引的模拟账户。
2. TransferArgs 的账号正则、金额范围及继承的严格校验（extra="forbid"）。
3. 先检查单笔 50000 限额，再检查余额的业务预检。
4. 扣款前确认转入账户存在，更新余额、执行计数和交易结果。
5. 注册高风险、必须审批、1.5 秒超时、零重试、非幂等的 transfer 工具。
6. 邮箱与账号递归脱敏；审计增加只包含脱敏转账目标的 safe_target 字段。
7. 五项测试覆盖非法参数、余额不足、超限、审批绑定和超时；审批测试同时检查正常转账、一次性审批和脱敏审计。

PermissionEngine.decide 保持与作业附录一致。测试显式配置 transfer 权限和白名单，默认上下文未扩大权限。

## 原题超时用例的冲突与处理

原题要求大于 50000 在预检阶段拒绝，同时要求 90000 进入 handler，触发大于 80000 的三秒延迟。由于预检先于 handler，这两项不能在完整原始路径中同时成立。

本实现保留全部业务阈值。第五个测试先验证 90000 返回 EXCEED_LIMIT，再以合法金额 100.0 和匹配审批注入测试专用慢 handler，仍通过真实 Runtime、真实预检、真实审批和真实 1.5 秒超时，验证 TIMEOUT_UNKNOWN、仅一次执行尝试及余额不变。未直接调用 transfer_handler，未修改权限引擎或放宽限额。

因此五项测试通过不表示“90000 在原始业务链中返回 TIMEOUT_UNKNOWN”；这是明确披露的测试设计调整，提交时应向教师说明。
