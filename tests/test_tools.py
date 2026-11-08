"""End-to-end checks of report.py and junit.py on small synthetic result files."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PY = sys.executable


def read(path):
    with open(path) as f:
        return f.read()


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)


def run(fail=False, p50=1500, mx=3000, late=0, lost=0, gap=22, outages=0, abandoned=0, restart_ms=None):
    return dict(fail=fail, p50=p50, p99=mx, max=mx, late=late, lost=lost, stalls=0, max_gap_ms=gap,
                outages=outages, abandoned=abandoned, restart_ms=restart_ms, outage_ms=None, checked=0, wrong=0)


def entry(profile, scenario, atk, prio, runs, extra=None):
    return dict(target="emulator", profile=profile, scenario=scenario, atk=atk, atk_prio=prio, extra=extra or {}, runs=runs)


def dataset():
    bad = lambda **k: run(fail=True, **k)
    none = [entry("none", "baseline (no attacker)", "", 10, [run()] * 5),
            entry("none", "cpu hog @prio 20", "cpu", 20, [bad(p50=2500000, gap=5000, mx=5000000)] * 5),
            entry("none", "workflood @prio 30", "workflood", 30, [bad(outages=8, lost=30)] * 5),
            entry("none", "mem hog @prio 10", "mem", 10, [run()] * 5)]
    prio = [entry("prio", e["scenario"], e["atk"], e["atk_prio"], [run()] * 5) for e in none]
    isolate = [entry("isolate", e["scenario"], e["atk"], e["atk_prio"],
                     [bad(outages=8, lost=30)] * 5 if e["atk"] == "workflood" else [run()] * 5) for e in none]
    return none, prio, isolate


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.files = []
        for name, rows in zip(("none", "prio", "isolate"), dataset()):
            p = os.path.join(self.tmp, f"{name}.json")
            write_json(p, rows)
            self.files.append(p)
        self.cfg = os.path.join(self.tmp, "siege.json")
        write_json(self.cfg, {"deadline_ms": 20, "scenarios": [
            {"label": "baseline (no attacker)"},
            {"label": "cpu hog @prio 20", "attacker": "cpu", "prio": 20, "expect": {"none": "fail"}},
            {"label": "workflood @prio 30", "attacker": "workflood", "prio": 30, "expect": {"none": "fail", "isolate": "fail"}},
            {"label": "mem hog @prio 10", "attacker": "mem", "prio": 10}]})

    def sh(self, script, *args):
        return subprocess.run([PY, os.path.join(ROOT, "scripts", script), *args], capture_output=True, text=True)

    def test_report_writes_everything_and_diagnoses(self):
        out = os.path.join(self.tmp, "rep")
        r = self.sh("report.py", *self.files, "--config", self.cfg, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        for ext in (".md", ".html", "-heatmap.svg", "-worst.svg"):
            self.assertTrue(os.path.getsize(out + ext) > 0, ext)
        md = read(out + ".md")
        self.assertIn("2 of 3 attacks", md)                      # cpu hog and workflood break the unhardened pipeline
        self.assertIn("pattern 1", md)
        self.assertIn("pattern 2", md)
        self.assertIn("Not helped by: isolate", md)              # isolation does not fix the shared-service flood
        self.assertIn("Measured in QEMU emulation", md)

    def test_report_draws_timelines_from_recorded_samples(self):
        rows = json.loads(read(self.files[0]))
        for r in rows:
            if r["scenario"] == "cpu hog @prio 20":
                for x in r["runs"]:
                    x["samples"] = [dict(t=1, late=0, lost=0, p50=1500, p99=3000, max=3000),
                                    dict(t=5, late=200, lost=0, p50=2500000, p99=4950000, max=4990000)]
        write_json(self.files[0], rows)
        out = os.path.join(self.tmp, "tl")
        self.sh("report.py", *self.files, "--config", self.cfg, "--out", out)
        self.assertIn("<polyline", read(out + ".html"))

    def test_report_flags_mixed_targets(self):
        rows = json.loads(read(self.files[0]))
        rows[0]["target"] = "hardware:root@pi"
        write_json(self.files[0], rows)
        out = os.path.join(self.tmp, "mixed")
        self.sh("report.py", *self.files, "--config", self.cfg, "--out", out)
        self.assertIn("mix emulator and hardware", read(out + ".md"))

    def test_junit_passes_when_behaviour_matches_expectations(self):
        out = os.path.join(self.tmp, "j.xml")
        r = self.sh("junit.py", *self.files, "--config", self.cfg, "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(out).count("<failure"), 0)

    def test_junit_fails_on_a_regression(self):
        rows = json.loads(read(self.files[1]))                   # the hardened profile starts failing
        rows[1]["runs"] = [run(fail=True, p50=2500000, gap=5000, mx=5000000)] * 5
        write_json(self.files[1], rows)
        out = os.path.join(self.tmp, "j2.xml")
        r = self.sh("junit.py", *self.files, "--config", self.cfg, "--out", out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISMATCH [prio] cpu hog @prio 20", r.stdout)
        self.assertEqual(read(out).count("<failure"), 1)

    def test_junit_keeps_the_entry_with_more_runs(self):
        extra = os.path.join(self.tmp, "deep.json")
        write_json(extra, [entry("none", "cpu hog @prio 20", "cpu", 20,
                         [run(fail=True, p50=2500000, gap=5000, mx=5000000)] * 15)])
        out = os.path.join(self.tmp, "j3.xml")
        r = self.sh("junit.py", *self.files, extra, "--config", self.cfg, "--out", out)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(read(out).count('name="cpu hog @prio 20"'), 3)   # one case per profile, not four

    def test_testreport_records_matches_and_mismatches(self):
        out = os.path.join(self.tmp, "tr")
        r = self.sh("testreport.py", *self.files, "--config", self.cfg, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        md = read(out + ".md")
        self.assertIn("test cases matched", md)
        self.assertIn("TC-EXE-01/none", md)
        self.assertIn("REQ-MSG", md)
        self.assertIn("not a certification claim", md)
        self.assertNotIn("MISMATCH", md)
        rows = json.loads(read(self.files[1]))                   # break the hardened profile
        rows[1]["runs"] = [run(fail=True, p50=2500000, gap=5000, mx=5000000)] * 5
        write_json(self.files[1], rows)
        self.sh("testreport.py", *self.files, "--config", self.cfg, "--out", out)
        self.assertIn("MISMATCH", read(out + ".md"))


class SceneInputTests(unittest.TestCase):
    def test_scene_is_wired_through(self):
        scene = read(os.path.join(ROOT, "pipeline", "scene.h"))
        self.assertIn("#define SCENE_N 16", scene)
        self.assertIn("Creative Commons", scene)
        self.assertIn("-s", read(os.path.join(ROOT, "pipeline", "frame_src.c")))
        self.assertIn("${SCENE:+-s}", read(os.path.join(ROOT, "image", "pipeline.sh")))
        self.assertIn("pipeline/scene.h", read(os.path.join(ROOT, "Makefile")))

    def test_scene_results_are_recorded(self):
        with open(os.path.join(ROOT, "docs", "results", "real-images.json")) as f:
            d = json.load(f)
        by = {r["max_background"]: r for r in d["rows"]}
        self.assertEqual(by[140]["exact"], 1.0)
        self.assertLess(by[255]["exact"], 0.9)


class FrontierTests(unittest.TestCase):
    def test_grid_and_replay(self):
        with open(os.path.join(ROOT, "docs", "results", "frontier-grid.json")) as f:
            d = json.load(f)
        self.assertEqual(len(d["cells"]), 54)
        r = subprocess.run([PY, os.path.join(ROOT, "scripts", "frontier.py"), "replay", "--seeds", "20", "--budgets", "14",
                            "--out", os.path.join(tempfile.mkdtemp(), "r.json")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| 14 of 54 |", r.stdout)

    def test_attacker_has_rate_knobs(self):
        self.assertIn("ATK_RATE", read(os.path.join(ROOT, "image", "pipeline.sh")))
        self.assertIn("frontier", read(os.path.join(ROOT, "siege")))


class SecpolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gen_secpol", os.path.join(ROOT, "tools", "gen_secpol.py"))
        cls.g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.g)

    def atk_block(self, text):
        start = text.index("allow atk_t self:ability {")
        return text[start:text.index("}", start)]

    def test_committed_policies_match_generator(self):
        for name, kw in self.g.VARIANTS.items():
            self.assertEqual(read(os.path.join(ROOT, "image", "secpol", name + ".secpol")), self.g.policy(name, **kw), name)

    def test_variants_restrict_what_they_claim(self):
        P = {n: self.g.policy(n, **kw) for n, kw in self.g.VARIANTS.items()}
        self.assertIn("allow atk_t det_t:channel connect;", P["open"])
        self.assertNotIn("allow atk_t det_t:channel connect;", P["connect"])
        self.assertIn("priority:1-9", P["ceiling"])
        self.assertNotIn("\n    priority\n", self.atk_block(P["ceiling"]))
        self.assertIn("\n    priority\n", self.atk_block(P["open"]))
        self.assertNotIn("pathspace", self.atk_block(P["names"]))
        self.assertIn("pathspace", self.atk_block(P["open"]))
        self.assertNotIn("allow_attach atk_t", P["names"])
        full = P["full"]
        self.assertNotIn("allow atk_t det_t:channel connect;", full)
        self.assertIn("priority:1-9", full)
        self.assertNotIn("pathspace", self.atk_block(full))

    def test_ceiling_is_below_the_pipeline(self):
        self.assertLess(self.g.CEILING, 10)       # equal priority already breaks the pipeline (docs/more-attackers.md)

    def test_every_variant_is_in_image_and_build(self):
        ram = read(os.path.join(ROOT, "image", "ram.build"))
        for name in self.g.VARIANTS:
            self.assertIn(f"secpol-{name}.bin=build/secpol-{name}.bin", ram)
        self.assertIn("bin/secpolpush", ram)
        self.assertIn("secpolcompile -m", read(os.path.join(ROOT, "scripts", "build.sh")))
        sh = read(os.path.join(ROOT, "image", "pipeline.sh"))
        self.assertIn("secpolpush /proc/boot/secpol-$SECPOL.bin", sh)
        self.assertIn("-T det_t", sh)
        self.assertIn("-T atk_t", sh)


if __name__ == "__main__":
    unittest.main()


class NewTooling(unittest.TestCase):
    ROOT = os.path.join(os.path.dirname(__file__), "..")

    def read(self, *p):
        with open(os.path.join(self.ROOT, *p)) as f:
            return f.read()

    def test_monitor_scale_matches_between_c_and_python(self):
        """The predictor's log scale must be the same in the controller (C) and the trainer (Python)."""
        import math, re
        c = float(re.search(r"#define MON_SCALE\s+([\d.]+)f", self.read("pipeline", "controller.c")).group(1))
        self.assertAlmostEqual(c, math.log1p(5_000_000), places=3)
        self.assertIn("SCALE = math.log1p(5_000_000)", self.read("tools", "train_monitor.py"))

    def test_search_command_is_registered(self):
        self.assertIn('"search": ("search.py"', self.read("siege"))
        self.assertTrue(os.path.exists(os.path.join(self.ROOT, "scripts", "search.py")))

    def test_vm_setup_script_is_valid_shell(self):
        import subprocess
        r = subprocess.run(["bash", "-n", os.path.join(self.ROOT, "scripts", "vm-setup.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_attacker_mode_is_documented(self):
        import re
        modes = set(re.findall(r'!strcmp\(mode, "(\w+)"\)', self.read("pipeline", "attacker.c"))) - {"child"}
        readme = self.read("README.md")
        for m in modes:
            self.assertIn(f"`{m}`", readme, f"attacker mode {m} is not in the README table")

    def test_siegewrap_is_in_the_image(self):
        self.assertIn("siegewrap=build/bin/siegewrap", self.read("image", "ram.build"))
        self.assertIn("siegewrap", self.read("Makefile"))


class TargetAddressing(unittest.TestCase):
    def test_host_port_is_split_for_forwarded_ssh(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from qnxconsole import split_host
        self.assertEqual(split_host("root@127.0.0.1:2222"), ("root@127.0.0.1", "2222"))
        self.assertEqual(split_host("root@10.0.0.5"), ("root@10.0.0.5", None))
        self.assertEqual(split_host("host:name"), ("host:name", None))

    def test_report_treats_labelled_emulator_targets_as_emulation(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "scripts", "report.py")) as f:
            src = f.read()
        self.assertIn('t.startswith("emulator")', src)

    def test_matrix_has_reboot_and_label_options(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "scripts", "matrix.py")) as f:
            src = f.read()
        for opt in ("--reboot-every", "--target-label"):
            self.assertIn(opt, src)

    def test_makefile_builds_for_either_architecture(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "Makefile")) as f:
            src = f.read()
        self.assertIn("ARCH    ?= aarch64le", src)
        self.assertIn("-Vgcc_nto$(ARCH)", src)


class ShowAndListTests(unittest.TestCase):
    """The no-install commands: they must work from a clean checkout and say true things."""

    def test_show_main_matrix_runs_without_qnx(self):
        out = subprocess.run([PY, os.path.join(ROOT, "siege"), "show", "--no-color"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("workflood @prio 30", out.stdout)
        row = [l for l in out.stdout.splitlines() if l.startswith("workflood @prio 30")][0].split()
        self.assertEqual(row[-4:], ["15/15", "1/15", "15/15", "15/15"])      # the headline finding, as committed

    def test_show_reads_given_files_and_colours_flaky_cells(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "r.json")
            write_json(f, [entry("none", "a", "cpu", 20, [run(fail=True)] * 2 + [run()] * 2),
                           entry("prio", "a", "cpu", 20, [run()] * 4)])
            out = subprocess.run([PY, os.path.join(ROOT, "siege"), "show", f, "--no-color"], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("2/4", out.stdout)
            self.assertIn("0/4", out.stdout)

    def test_show_rejects_files_with_no_results(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "x.json")
            write_json(f, {"not": "results"})
            out = subprocess.run([PY, os.path.join(ROOT, "siege"), "show", f], capture_output=True, text=True)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn("no scenario results", out.stderr)

    def test_list_names_profiles_and_scenarios(self):
        out = subprocess.run([PY, os.path.join(ROOT, "siege"), "list", "--config",
                              os.path.join(ROOT, "examples", "secpol", "siege.json")], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        for word in ("secpol-ceiling", "workflood", "name squat"):
            self.assertIn(word, out.stdout)

    def test_readme_start_here_commands_exist(self):
        text = read(os.path.join(ROOT, "README.md"))
        self.assertIn("## Start here", text)
        for cmd in ("show", "list", "doctor"):
            self.assertIn(f"./siege {cmd}", text)
            self.assertIn(cmd, read(os.path.join(ROOT, "siege")))


class SecpolDocTests(unittest.TestCase):
    def test_security_policy_doc_links_resolve(self):
        import re
        doc = os.path.join(ROOT, "docs", "security-policy.md")
        text = read(doc)
        for target in re.findall(r"\]\((\.\./[^)#]+|[a-z][^):#]+)\)", text):
            self.assertTrue(os.path.exists(os.path.normpath(os.path.join(ROOT, "docs", target))), target)

    def test_every_secpol_scenario_has_declared_expectations(self):
        with open(os.path.join(ROOT, "examples", "secpol", "siege.json")) as f:
            cfg = json.load(f)
        declared = [s for s in cfg["scenarios"] if "expect" in s]
        self.assertGreaterEqual(len(declared), 9)
        for s in declared:
            self.assertEqual(set(s["expect"]), set(cfg["profiles"]), s["label"])


class DevOpsFilesTests(unittest.TestCase):
    def test_workflow_parses_and_only_uses_real_commands(self):
        import yaml
        with open(os.path.join(ROOT, ".github", "workflows", "ci.yml")) as f:
            wf = yaml.safe_load(f)
        self.assertEqual(set(wf["jobs"]), {"tests", "evidence", "docker"})
        text = read(os.path.join(ROOT, ".github", "workflows", "ci.yml"))
        for path in ("scripts/junit.py", "scripts/results_files.py", "examples/secpol/siege.json", "docker/builder/Dockerfile"):
            self.assertIn(path, text)
            self.assertTrue(os.path.exists(os.path.join(ROOT, path)), path)

    def test_declared_expectations_still_match_committed_results(self):
        out = subprocess.run([PY, os.path.join(ROOT, "scripts", "junit.py"), "--config",
                              os.path.join(ROOT, "examples", "secpol", "siege.json"),
                              *sorted(__import__("glob").glob(os.path.join(ROOT, "examples", "secpol", "results", "*.json"))),
                              "--out", os.devnull], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_dockerfile_keeps_qnx_and_notes_out(self):
        ignore = read(os.path.join(ROOT, ".dockerignore"))
        for item in (".git", ".notes", "build"):
            self.assertIn(item, ignore)
        for f in ("Dockerfile", os.path.join("docker", "builder", "Dockerfile")):
            text = read(os.path.join(ROOT, f))
            self.assertNotIn("COPY /opt", text)
            self.assertNotIn("qnx800.run", text)


class TraceMarkTests(unittest.TestCase):
    def test_controller_marks_are_off_by_default_and_documented(self):
        src = read(os.path.join(ROOT, "pipeline", "controller.c"))
        self.assertIn('getenv("SIEGE_TRACE")', src)
        self.assertIn("_NTO_TRACE_INSERTUSRSTREVENT", src)
        self.assertIn("if (!trace_marks_on", src)             # nothing is written unless asked, so measurements are unchanged
        doc = read(os.path.join(ROOT, "docs", "trace-marks.md"))
        self.assertIn("USREVENT", doc)
        self.assertIn("SIEGE_TRACE=1", read(os.path.join(ROOT, "scripts", "trace_capture.py")))
