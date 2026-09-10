"""通过真实 Runtime 验证转账治理；不直接调用 transfer_handler。

原题 90000 会被 50000 限额预检拦截。超时用例保留该拒绝断言，
再用合法金额和测试专用慢 handler 验证真实 Runtime 的超时策略。
"""

import asyncio
import json
from dataclasses import asdict, replace
from unittest.mock import AsyncMock

import pytest

import tool_governance_demo as demo


@pytest.fixture(autouse=True)
def isolated_state():
    accounts = demo.ACCOUNTS.copy()
    effects = demo.SIDE_EFFECTS.copy()
    demo.reset_side_effects()
    try:
        yield
    finally:
        demo.ACCOUNTS.clear()
        demo.ACCOUNTS.update(accounts)
        demo.SIDE_EFFECTS.clear()
        demo.SIDE_EFFECTS.update(effects)


def transfer_context():
    return demo.base_context(
        permissions=frozenset({"transfer:execute"}),
        allowed_tools=frozenset({"transfer"}),
    )


def arguments(amount=100.0, from_account="ACC-A-123456"):
    return {
        "from_account": from_account,
        "to_account": "ACC-A-888888",
        "amount": amount,
    }


def invoke(runtime, payload, context, call_id="call_transfer_000001"):
    return asyncio.run(
        runtime.invoke(demo.ToolCall(call_id, "transfer", payload), context)
    )


def assert_rejected_without_effect(result, code, before):
    assert result.code == code
    assert not result.ok
    assert result.action is demo.DecisionAction.DENY
    assert demo.SIDE_EFFECTS["transfer_executions"] == 0
    assert demo.ACCOUNTS == before


def test_transfer_schema_rejects_extra():
    runtime, _, audit = demo.build_runtime()
    context = transfer_context()
    before = demo.ACCOUNTS.copy()
    assert demo.TransferArgs.model_config["extra"] == "forbid"
    invalid_payloads = [
        {**arguments(), "from_account": "ACC-A-12345"},
        {**arguments(), "to_account": "ACC-A-1234567"},
        {**arguments(), "approved": True},
        arguments(0.0),
        arguments(100001.0),
    ]
    for index, payload in enumerate(invalid_payloads):
        call_id = f"call_invalid_{index}"
        result = invoke(runtime, payload, context, call_id)
        assert_rejected_without_effect(result, "INVALID_ARGUMENT", before)
        assert result.tool_call_id == call_id
    assert all(record.phase == "decision" for record in audit.records)


def test_transfer_precheck_insufficient():
    runtime, _, audit = demo.build_runtime()
    before = demo.ACCOUNTS.copy()
    result = invoke(runtime, arguments(6000.0, "ACC-A-654321"), transfer_context())
    assert_rejected_without_effect(result, "INSUFFICIENT_BALANCE", before)
    assert len(audit.records) == 1
    assert audit.records[0].phase == "decision"


def test_transfer_precheck_exceed_limit():
    runtime, _, _ = demo.build_runtime()
    before = demo.ACCOUNTS.copy()
    # 余额充足和不足时都应先返回限额错误，证明检查顺序。
    for source in ("ACC-A-123456", "ACC-A-654321"):
        result = invoke(runtime, arguments(60000.0, source), transfer_context())
        assert_rejected_without_effect(result, "EXCEED_LIMIT", before)


def test_transfer_approval_binding():
    runtime, approvals, audit = demo.build_runtime()
    context = transfer_context()
    before = demo.ACCOUNTS.copy()
    payload = arguments()

    pending = invoke(runtime, payload, context, "call_pending")
    assert pending.code == "APPROVAL_REQUIRED"
    assert pending.action is demo.DecisionAction.CONFIRM
    assert not pending.ok
    assert demo.ACCOUNTS == before
    assert demo.SIDE_EFFECTS["transfer_executions"] == 0

    # 对验证后的参数审批，避免 100 与 100.0 的 JSON 表示差异。
    print(f"Before approval: {pending.action.name} ({pending.code})")
    approvals.approve("approval_transfer", context, "transfer", demo.TransferArgs(**payload))
    approved_context = replace(context, approval_id="approval_transfer")
    changed = invoke(runtime, arguments(200.0), approved_context, "call_changed")
    assert changed.code == "APPROVAL_REQUIRED"
    assert changed.action is demo.DecisionAction.CONFIRM
    assert not changed.ok
    assert demo.ACCOUNTS == before
    assert demo.SIDE_EFFECTS["transfer_executions"] == 0

    # 原金额仍能成功，排除“审批无论参数如何都无效”的假通过。
    result = invoke(runtime, payload, approved_context, "call_success_123456")
    assert result.ok and result.code == "OK"
    assert result.tool_call_id == "call_success_123456"
    assert result.content == {
        "txn_id": "123456",
        "from": "ACC-A-****3456",
        "to": "ACC-A-****8888",
        "amount": 100.0,
        "status": "completed",
    }
    assert demo.ACCOUNTS[("tenant_a", payload["from_account"])] == 99900.0
    assert demo.ACCOUNTS[("tenant_a", payload["to_account"])] == 20100.0
    assert demo.ACCOUNTS[("tenant_a", "ACC-A-654321")] == 5000.0
    assert demo.ACCOUNTS[("tenant_b", "ACC-B-111111")] == 50000.0
    assert sum(demo.ACCOUNTS.values()) == sum(before.values())
    assert demo.SIDE_EFFECTS["transfer_executions"] == 1

    after = demo.ACCOUNTS.copy()
    replay = invoke(runtime, payload, approved_context, "call_replay")
    assert replay.code == "APPROVAL_REQUIRED"
    assert replay.action is demo.DecisionAction.CONFIRM
    assert demo.ACCOUNTS == after
    assert demo.SIDE_EFFECTS["transfer_executions"] == 1
    executed = [record for record in audit.records if record.decision == "executed"]
    assert len(executed) == 1
    assert executed[0].tool_call_id == result.tool_call_id
    expected_target = "ACC-A-****3456->ACC-A-****8888"
    assert all(record.safe_target == expected_target for record in audit.records)
    assert audit.records[0].decision == demo.DecisionAction.CONFIRM
    audit_json = json.dumps([asdict(record) for record in audit.records], ensure_ascii=False)
    assert payload["from_account"] not in audit_json
    assert payload["to_account"] not in audit_json
    assert expected_target in audit_json
    print(f"Audit: {audit_json}")


def test_transfer_timeout_no_retry():
    context = transfer_context()
    before = demo.ACCOUNTS.copy()
    runtime, _, _ = demo.build_runtime()
    rejected = invoke(runtime, arguments(90000.0), context)
    assert_rejected_without_effect(rejected, "EXCEED_LIMIT", before)

    # 只替换工具的业务耗时，不替换 Runtime、预检、审批或超时机制。
    async def slow_handler(tool_call_id, args, context):
        await asyncio.sleep(3.0)
        raise AssertionError("1.5 秒超时应在此之前取消 handler")

    probe = AsyncMock(side_effect=slow_handler)
    tools = demo.build_tools()
    transfer = next(tool for tool in tools if tool.name == "transfer")
    assert transfer.policy.effect is demo.Effect.WRITE
    assert transfer.policy.requires_approval
    assert transfer.policy.timeout_seconds == 1.5
    assert transfer.policy.max_retries == 0
    assert transfer.policy.idempotent is False
    tools = [replace(tool, handler=probe) if tool.name == "transfer" else tool for tool in tools]
    approvals = demo.ApprovalStore()
    audit = demo.AuditSink()
    runtime = demo.ToolRuntime(tools, demo.PermissionEngine(demo.DEFAULT_RULES, approvals), audit)
    payload = arguments(100.0)
    approvals.approve("approval_timeout", context, "transfer", demo.TransferArgs(**payload))
    result = invoke(runtime, payload, replace(context, approval_id="approval_timeout"), "call_timeout")

    assert not result.ok
    assert result.code == "TIMEOUT_UNKNOWN"
    assert result.retryable is False
    assert result.tool_call_id == "call_timeout"
    assert probe.await_count == 1
    assert demo.SIDE_EFFECTS["transfer_executions"] == 0
    assert demo.ACCOUNTS == before
    assert [(record.phase, record.code) for record in audit.records] == [
        ("decision", "APPROVED"),
        ("execution", "TIMEOUT_UNKNOWN"),
    ]
