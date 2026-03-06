# Contributing

Thank you for your interest in this artifact repository.

## Reporting Issues

If you encounter problems reproducing the results, please open a GitHub issue with:

1. Your host OS and Docker version (`docker --version`)
2. The failing script name and full command
3. The relevant portion of the log from `logs/build/` or `logs/run/`
4. The gate number that failed (Gate 3–9)

## Validation Gates

Before submitting any changes, verify that the basic gate sequence passes:

```bash
scripts/run_gate3_container.sh           # Boot checkpoint
scripts/run_gate5_command_smoke.sh       # SE-PIM command surface smoke test
scripts/run_gate9_kmeans.sh --quick      # Quick k-means smoke run
```

## Pull Requests

This is a research artifact. Pull requests are welcome for:
- Bug fixes in run/plot scripts
- Documentation improvements
- Portability improvements (e.g., additional platform support)

Please do **not** modify the simulation source (IMPICA/gem5/) in ways that change the experiment results, as that would break reproducibility.

## Code Style

- Shell scripts: POSIX-compatible bash, `set -euo pipefail` at the top
- Python: stdlib only (no external pip dependencies), compatible with Python 3.8+
