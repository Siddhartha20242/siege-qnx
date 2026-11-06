import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import siegelib as L


def run(fail=False, p50=1500, mx=3000, late=0, lost=0, gap=22, outages=0, abandoned=0):
    return dict(fail=fail, p50=p50, max=mx, late=late, lost=lost, max_gap_ms=gap, outages=outages, abandoned=abandoned)


class Wilson(unittest.TestCase):
    def test_zero_of_five_has_wide_upper_bound(self):
        self.assertEqual(L.wilson(0, 5), (0, 43))

    def test_all_of_five_and_fifteen(self):
        self.assertEqual(L.wilson(5, 5), (57, 100))
        self.assertEqual(L.wilson(15, 15), (80, 100))

    def test_no_runs_means_no_information(self):
        self.assertEqual(L.wilson(0, 0), (0, 100))

    def test_interval_brackets_the_rate(self):
        lo, hi = L.wilson(7, 20)
        self.assertLessEqual(lo, 35)
        self.assertGreaterEqual(hi, 35)


class Verdict(unittest.TestCase):
    def test_threshold_is_inclusive(self):
        self.assertEqual(L.observed_verdict(1, 5), "pass")     # 20%
        self.assertEqual(L.observed_verdict(2, 5), "fail")     # 40%

    def test_no_runs_is_a_fail(self):
        self.assertEqual(L.observed_verdict(0, 0), "fail")


class Aggregate(unittest.TestCase):
    def test_sums_and_maxima(self):
        a = L.aggregate([run(), run(fail=True, late=5, mx=9000, gap=300), None])
        self.assertEqual((a["n"], a["fails"], a["late"], a["worst"], a["gap"]), (3, 1, 5, 9000, 300))

    def test_all_missing_is_none(self):
        self.assertIsNone(L.aggregate([None, None]))


class Diagnose(unittest.TestCase):
    def agg(self, **kw):
        return L.aggregate([run(fail=True, **kw)] * 3)

    def test_passing_scenario_has_no_pattern(self):
        self.assertIsNone(L.diagnose("cpu", 20, L.aggregate([run()] * 3)))

    def test_cpu_hog_above_pipeline_that_starves(self):
        self.assertEqual(L.diagnose("cpu", 20, self.agg(p50=2500000, gap=5000, mx=5000000)), 1)

    def test_message_flood_is_queue_priority_starvation(self):
        self.assertEqual(L.diagnose("workflood", 30, self.agg(outages=10, lost=30)), 2)

    def test_pipe_manager_flood_is_queue_priority_starvation(self):
        self.assertEqual(L.diagnose("pipeflood", 30, self.agg(late=400, p50=300000, mx=900000)), 2)

    def test_ai_neighbour_is_burst_interference(self):
        self.assertEqual(L.diagnose("ai", 20, self.agg(late=40, mx=44000)), 3)

    def test_same_priority_neighbour_is_timeslice_jitter(self):
        self.assertEqual(L.diagnose("cpu", 10, self.agg(late=10, mx=11000)), 4)

    def test_abandoned_run_is_a_dead_service(self):
        self.assertEqual(L.diagnose("", 10, self.agg(abandoned=1)), 5)

    def test_every_pattern_has_a_title_and_a_fix(self):
        for pid, (title, fix) in L.PATTERNS.items():
            self.assertTrue(title and fix, pid)


class BuildCommand(unittest.TestCase):
    cfg = {"deadline_ms": 20, "tolerance_permille": 20, "recovery_ms": 500,
           "profiles": ["none", "prio"], "scenarios": []}

    def test_builtin_pipeline_command(self):
        cmd = L.build_command(self.cfg, {"attacker": "cpu", "prio": 20}, "prio", 5)
        self.assertTrue(cmd.endswith("pipeline.sh 5"))
        for want in ('PROFILE=prio', 'ATK="cpu"', "ATK_PRIO=20", "DEADLINE_MS=20", "TOL_PM=20"):
            self.assertIn(want, cmd)

    def test_scenario_env_and_global_env_are_applied(self):
        cfg = dict(self.cfg, env={"DET_MODEL": "cnn"})
        cmd = L.build_command(cfg, {"env": {"KILL_AT": 2, "SUPERVISE": 1}}, "none", 6)
        for want in ("DET_MODEL=cnn", "KILL_AT=2", "SUPERVISE=1"):
            self.assertIn(want, cmd)

    def test_external_program_uses_the_harness_and_profile_env(self):
        cfg = {"pipeline": {"command": "ticker -d {dur}"}, "profiles": {"none": {}, "prio": {"PIPE_PRIO": 40}}}
        cmd = L.build_command(cfg, {"attacker": "cpu", "prio": 20}, "prio", 7)
        self.assertIn("PIPE_PRIO=40", cmd)
        self.assertTrue(cmd.endswith("harness.sh 7 ticker -d 7"))

    def test_hardware_turns_off_the_emulator_workaround(self):
        self.assertIn("IDLE_POLL=0", L.build_command(self.cfg, {}, "none", 5, ssh=True))
        self.assertNotIn("IDLE_POLL", L.build_command(self.cfg, {}, "none", 5))


if __name__ == "__main__":
    unittest.main()
