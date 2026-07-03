"""Global test isolation: NO test may touch production QA state.

The trust pipeline's stores default to cwd-relative production paths
(output/.qa/...). Every default is redirected to a per-test tmp dir here,
autouse, so a test that forgets to inject paths pollutes a sandbox instead
of the operator's real ledger/approvals. (Born of a real incident: endpoint
tests wrote 85 fake records into the production reliability ledger.)
"""

import pytest

import backend.qa.approvals as approvals_mod
import backend.qa.reliability as reliability_mod


@pytest.fixture(autouse=True)
def _isolate_qa_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        reliability_mod, "DEFAULT_LEDGER_PATH", tmp_path / "_isolated_reliability.jsonl"
    )
    monkeypatch.setattr(
        approvals_mod, "_default_store",
        approvals_mod.ApprovalStore(tmp_path / "_isolated_approvals.json"),
    )
    yield
