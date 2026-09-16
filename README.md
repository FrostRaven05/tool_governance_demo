# 第二章转账作业（2026-09-16 修订版）

本包按 2026-09-16 作业与目录新增的配套脚本/五项测试更新。旧版研究中的“90000 超时不可达”结论已不适用于新版。

## 运行

Python 3.11+（验收使用 Python 3.12）。解压进入本目录：

```bash
python -m pip install -r requirements.txt
python -m pytest tests/test_tool_governance.py -v -k "transfer"
```

显示审批状态与脱敏审计：

```bash
python -m pytest tests/test_tool_governance.py -v -s -k "transfer"
```

`python tool_governance_demo.py` 运行原有订单/退款/Shell 离线演示。转账由测试覆盖。不需要模型密钥。

## 新版规则与实现

- 仅 50000 < amount <= 80000 返回 EXCEED_LIMIT，这是教学规则。
- 超过 80000 仍检查余额及审批；90000 在获批后进入真实 transfer_handler 的 sleep(3.0)。
- 沿用本次提供脚本的 2.0 秒超时、零重试、非幂等配置及 accepted 状态。当前作业.md 的工具配置表和测试表未包含具体内容，以随附脚本与测试为准。
- 超时测试不替换 handler、不注入延迟，不直接调用 handler，完整调用经过 runtime.invoke。
- 使用本次提供的五项测试，覆盖参数注入、业务预检、权限/白名单/PLAN、审批/成功/脱敏以及真实超时。
- 审计增加 safe_target，入库前账号脱敏；审批测试打印 CONFIRM 和审计记录，并验证原始账号没有泄漏。
- PermissionEngine.decide 与本次提供的版本保持 AST 一致，StrictArgs 的 extra="forbid" 保留。

原始新测试仍保留在工作区第二章/test_tool_governance.py；提交使用 tests/ 下带审计输出验证的版本。
