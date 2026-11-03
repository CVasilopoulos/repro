from app.verdict import RefRun, containment_signals, decide


def run(setup=0, exits=(1, 1), lost=""):
    return RefRun(ref="x", commit="c", setup_exit=setup, repro_exits=list(exits), lost=lost)


def test_bug_present_at_both_refs_is_reproduced():
    assert decide(run(exits=(1, 1)), run(exits=(1, 1)))[0] == "reproduced"


def test_bug_present_only_at_reported_ref_is_fixed():
    assert decide(run(exits=(1, 1)), run(exits=(0, 0)))[0] == "fixed"


def test_bug_absent_at_both_refs_is_not_reproducible():
    assert decide(run(exits=(0, 0)), run(exits=(0, 0)))[0] == "not_reproducible"


def test_bug_only_on_default_branch_is_reported_as_new():
    assert decide(run(exits=(0, 0)), run(exits=(1, 1)))[0] == "new_on_default"


def test_failed_setup_makes_the_verdict_inconclusive():
    verdict, why = decide(run(setup=2), run())
    assert verdict == "inconclusive" and "reported ref" in why


def test_unexpected_exit_code_makes_the_verdict_inconclusive():
    assert decide(run(), run(exits=(139, 139)))[0] == "inconclusive"


def test_lost_sandbox_makes_the_verdict_inconclusive():
    assert decide(run(lost="OOM"), run())[0] == "inconclusive"


def test_disagreeing_repeat_runs_are_flaky():
    assert decide(run(exits=(1, 0)), run(exits=(1, 1)))[0] == "flaky"


def test_read_only_root_and_fork_failures_are_detected():
    out = "rm: cannot remove '/usr/bin/ls': Read-only file system\nbash: fork: retry: Resource temporarily unavailable\n"
    signals = {h["signal"] for h in containment_signals("bash x.sh", out)}
    assert {"read_only_root", "process_limit"} <= signals


def test_gate_refusal_and_metadata_probe_are_detected():
    out = "curl: (56) CONNECT tunnel failed, response 403\nrepro egress gate: cloud metadata endpoint\n"
    signals = {h["signal"] for h in containment_signals("curl http://169.254.169.254/v1.json", out)}
    assert {"egress_blocked", "metadata_probe"} <= signals


def test_clean_output_has_no_signals():
    assert containment_signals("pytest -q", "3 passed in 0.12s\n") == []


def test_every_lab_preset_has_a_bounded_timeout_and_explanation():
    from app.lab import PRESETS

    for key, spec in PRESETS.items():
        assert spec["title"] and spec["explain"] and spec["command"]
        assert 0 < spec["timeout"] <= 120, key
