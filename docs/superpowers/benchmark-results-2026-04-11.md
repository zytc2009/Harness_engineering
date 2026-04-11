# Benchmark Results

Date: 2026-04-11

## Scope

Evaluate the end-to-end benchmark path using the task documents under:

- `docs/tasks/benchmarks/`

## Benchmark Inputs

1. `docs/tasks/benchmarks/python-log-summarizer.md`
2. `docs/tasks/benchmarks/cpp-config-loader.md`
3. `docs/tasks/benchmarks/runtime-readme-refresh.md`

## Commands Run

```bash
python harness-runtime/main.py --validate-task-doc docs/tasks/benchmarks/python-log-summarizer.md
python harness-runtime/main.py --validate-task-doc docs/tasks/benchmarks/cpp-config-loader.md
python harness-runtime/main.py --validate-task-doc docs/tasks/benchmarks/runtime-readme-refresh.md

python harness-runtime/main.py --add-file docs/tasks/benchmarks/python-log-summarizer.md
python harness-runtime/main.py --add-file docs/tasks/benchmarks/cpp-config-loader.md
python harness-runtime/main.py --add-file docs/tasks/benchmarks/runtime-readme-refresh.md

python harness-runtime/main.py --drain
python harness-runtime/main.py --queue-json
python harness-runtime/main.py --status-json
```

## Result Summary

- task document validation: passed for all 3 benchmark docs
- enqueue path: passed for all 3 benchmark docs
- queue/status JSON views: passed and reflected expected task metadata
- drain execution from the agent sandbox: failed for all 3 tasks at architect phase due external model connection failure
- provider probe rerun outside the sandbox: passed for `architect`, `implementer`, and `tester`

## Observed Runtime Outcome

Final queue state:

- `0` pending
- `0` running
- `0` done
- `3` failed

Observed failure mode for every task inside the restricted agent sandbox:

- `status = failed`
- `phase = error`
- `retry_count = 0`
- `error = "Connection error."`

This means the sandboxed benchmark run successfully exercised:

- task document validation
- markdown-to-queue normalization
- constraint parsing
- harness metadata propagation
- queue execution state transitions
- worker status snapshots

This run did not validate:

- successful architect generation
- implementer/tester execution
- retry-after-test-failure behavior on real benchmark tasks

## Conclusion

The current blocker observed during the first benchmark drain was not task-doc quality or queue wiring.

The blocker was the agent sandbox network restriction during `--drain`.

This is now distinguished from the real runtime/provider state:

- `python probe.py` inside the sandbox returned `Connection error.`
- the same probe rerun outside the sandbox returned successful replies from all 3 configured phase models

So the benchmark drain failure in this session should not be interpreted as a repo-level provider misconfiguration.

## Next Step

Repeat the same benchmark run outside the restricted sandbox or from the user's terminal, then record:

- success/failure rate by benchmark
- retry counts
- final artifacts written to sandbox
- whether harness-specific context changes behavior for the C++ task
