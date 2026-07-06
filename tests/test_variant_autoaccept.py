"""M6: variant phase auto-accepts judge passes, queues the rest (D-003)."""

from types import SimpleNamespace

from backend.onboarding import onboard_variants
from backend.qa.approvals import get_approval_store


class FakeProject:
    def __init__(self):
        self.generation_status = "idle"
        self.results = []
        self.qa_verdicts = {}
        self.selected_swatches = []


class FakeStore:
    def __init__(self, project):
        self._p = project

    def get(self, _pid):
        return self._p

    def update(self, _pid, **kw):
        for k, v in kw.items():
            setattr(self._p, k, v)
        return self._p


def _rec(image_id, wood):
    return SimpleNamespace(image_id=image_id, wood_name=wood)


def _done(gate):
    return {"qa_status": "done", "gates_as": gate, "verdict": gate}


def test_auto_accepts_passes_and_queues_the_rest():
    project = FakeProject()

    def fake_generate(store, proj, api_key):
        proj.results = [
            _rec("v1", "White Supermatte"),
            _rec("v2", "Gauntlet Grey"),
            _rec("v3", "Green Supermatte"),
            _rec("v4", "White Woodgrain"),
        ]
        proj.qa_verdicts = {
            "v1": _done("pass"),
            "v2": _done("pass"),
            "v3": _done("needs_human"),
            "v4": _done("regenerate"),  # cap exhausted, still weak
        }
        proj.generation_status = "done"

    store = FakeStore(project)
    result = onboard_variants(
        store, "pid-KB732", "key", ["a.jpg", "b.jpg", "c.jpg", "d.jpg"],
        generate_fn=fake_generate, timeout=5, poll=0.1, stable_polls=1,
        reset_existing=False,
    )

    assert result["total"] == 4
    assert sorted(result["accepted"]) == ["Gauntlet Grey", "White Supermatte"]
    queued_woods = sorted(w for w, _ in result["queued"])
    assert queued_woods == ["Green Supermatte", "White Woodgrain"]

    # passes got approval records; unsure ones did not
    approved = {a.image_id for a in get_approval_store().for_project("pid-KB732")
                if a.verdict == "approved"}
    assert approved == {"v1", "v2"}
