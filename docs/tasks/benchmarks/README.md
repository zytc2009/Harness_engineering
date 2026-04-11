# Benchmark Task Docs

These task documents exist to exercise the current task-doc and runtime boundary on realistic examples.

They are not runtime output files. They are benchmark inputs for:

```bash
python harness-runtime/main.py --validate-task-doc <path>
python harness-runtime/main.py --add-file <path>
```

## Included Cases

- `python-log-summarizer.md`
  - generic language task without a concrete harness
- `cpp-config-loader.md`
  - C++ task that explicitly selects `harness-cpp`
- `runtime-readme-refresh.md`
  - repo-internal documentation task with path constraints

## Purpose

Use these tasks to verify that:

- task documents are specific enough to enqueue without follow-up questions
- `Constraints` parsing behaves correctly
- harness selection works when requested
- queue/runtime behavior can be exercised on something closer to real work than unit-test fixtures
