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

上述默认离线演示保留原附录的订单/退款/Shell 场景；转账完整演示在审批绑定测试中完成。所有账户与转账均为内存模拟，不需要 API Key。
