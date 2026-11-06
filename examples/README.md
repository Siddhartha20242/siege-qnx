# Examples

Each folder is a self-contained use of Siege. Run any of them with
`./siege test --config examples/<name>/siege.json --profile <profile>`.

| Folder | What it shows |
|---|---|
| [`ticker/`](ticker/) | A second, unrelated real-time program (a 100 Hz periodic task, 5 ms deadline). It is more fragile than the reference pipeline: it fails even against a same-priority CPU hog, and a higher priority fixes it. About seventy lines of C. |
| [`pipeprobe/`](pipeprobe/) | A program whose latency goes *through a QNX system service*: the `pipe` manager. Tests whether the queue-priority pattern appears in a real service and not only in Siege's own detector. |
| [`adas/`](adas/) | The reference pipeline configured as a 30 Hz front-camera driver-assistance stack (33 ms deadline) with lower-criticality tasks on the same machine. 36 of 36 cases matched; see [`../docs/adas-isolation.md`](../docs/adas-isolation.md). |
| [`wrap/`](wrap/) | `siegewrap` testing a program that was not written for Siege and prints nothing: a canary task and a liveness check supply the result. |
| [`cnn/`](cnn/) | The reference pipeline with a trained convolutional network as the detector (`DET_MODEL=cnn`), checked against ground truth. The headline findings re-run with it. |
| [`ci/`](ci/) | A GitHub Actions workflow that runs Siege on every change and fails the build when isolation regresses. |

To add your own program, see "Testing your own program" in the
[main README](../README.md), or run `./siege init <name> --command "<how to run it>"`.
