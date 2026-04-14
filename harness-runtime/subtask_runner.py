"""Subtask runner for decomposed pipeline execution."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import git_ops
from orchestrator import architect_phase, implementer_phase, tester_phase

logger = logging.getLogger(__name__)


@dataclass
class SubtaskResult:
    subtask_id: int
    title: str
    status: str          # "passed" | "skipped"
    retry_count: int
    commit_sha: str      # empty on git failure or skip
    error: str           # empty on success


def _resolve_workspace(
    workspace_dir: str | Path | None,
    sandbox_dir: Path,
) -> Path:
    """Return the directory to write files and commit into."""
    if workspace_dir is not None:
        path = Path(workspace_dir)
        path.mkdir(parents=True, exist_ok=True)
        git_ops.ensure_git_repo(path)
        return path
    git_ops.ensure_git_repo(sandbox_dir)
    return sandbox_dir


def _should_run_tester(
    constraints: dict,
    subtask_index: int,
    total: int,
) -> bool:
    last_only = str(constraints.get("subtask_tester_last_only", "false")).lower() == "true"
    if last_only:
        return subtask_index == total - 1
    return str(constraints.get("subtask_tester", "false")).lower() == "true"


def _run_subtask(
    task: str,
    design: str,
    subtask: dict,
    subtask_index: int,
    total: int,
    workspace: Path,
    sandbox_dir: Path,
    max_retries: int,
    run_tester: bool,
    on_status: Callable | None,
    task_metadata: dict | None,
) -> SubtaskResult:
    idx = subtask["id"]
    title = subtask["title"]
    description = subtask.get("description", "")
    files = subtask.get("files", [])
    acceptance_criteria = subtask.get("acceptance_criteria", "")

    subtask_prompt = (
        f"Task: {task}\n\n"
        f"## Overall Design\n{design}\n\n"
        f"## Current Subtask ({idx}/{total}): {title}\n{description}\n\n"
        f"## Acceptance Criteria\n{acceptance_criteria}\n\n"
        f"## Files to implement\n"
        + "\n".join(f"- {f}" for f in files)
    )

    retry_count = 0
    tester_report = ""

    while True:
        _emit(on_status, "subtask_started", idx, total, "architect",
              f"subtask {idx}/{total} architect")

        sub_design = architect_phase(
            subtask_prompt, sandbox_dir=sandbox_dir, task_metadata=task_metadata,
        )

        _emit(on_status, "subtask_started", idx, total, "implementer",
              f"subtask {idx}/{total} implementer")

        code_files = implementer_phase(
            subtask_prompt, sub_design,
            feedback=tester_report,
            sandbox_dir=workspace,
            task_metadata=task_metadata,
        )

        if not code_files:
            retry_count += 1
            tester_report = "implementer produced no parseable FILE blocks"
            if retry_count >= max_retries:
                return SubtaskResult(
                    subtask_id=idx, title=title, status="skipped",
                    retry_count=retry_count, commit_sha="", error=tester_report,
                )
            continue

        commit_sha = _try_commit(workspace, files or list(code_files.keys()), idx, total, title, acceptance_criteria)

        if not run_tester:
            return SubtaskResult(
                subtask_id=idx, title=title, status="passed",
                retry_count=retry_count, commit_sha=commit_sha, error="",
            )

        _emit(on_status, "subtask_started", idx, total, "tester",
              f"subtask {idx}/{total} tester")

        passed, tester_report = tester_phase(
            subtask_prompt, sub_design, code_files,
            sandbox_dir=workspace, task_metadata=task_metadata,
        )

        if passed:
            return SubtaskResult(
                subtask_id=idx, title=title, status="passed",
                retry_count=retry_count, commit_sha=commit_sha, error="",
            )

        retry_count += 1
        if retry_count >= max_retries:
            return SubtaskResult(
                subtask_id=idx, title=title, status="skipped",
                retry_count=retry_count, commit_sha=commit_sha,
                error=tester_report[:200],
            )
        continue  # restart loop: re-run architect + implementer with tester feedback


def _try_commit(
    workspace: Path,
    files: list[str],
    idx: int,
    total: int,
    title: str,
    acceptance_criteria: str,
) -> str:
    message = (
        f"[subtask {idx}/{total}] {title}\n\n"
        f"acceptance_criteria: {acceptance_criteria}"
    )
    try:
        return git_ops.commit_subtask(workspace, files, message)
    except Exception as exc:
        logger.warning("git commit failed for subtask %d: %s", idx, exc)
        return ""


def _emit(
    on_status: Callable | None,
    event_type: str,
    subtask_id: int,
    subtask_total: int,
    phase: str | None,
    message: str,
) -> None:
    if on_status is None:
        return
    on_status({
        "type": event_type,
        "subtask_id": subtask_id,
        "subtask_total": subtask_total,
        "phase": phase,
        "message": message,
    })


def run_subtasks(
    task: str,
    design: str,
    subtasks: list[dict],
    sandbox_dir: Path,
    workspace_dir: str | Path | None,
    max_retries: int,
    on_status: Callable | None,
    task_metadata: dict | None,
) -> list[SubtaskResult]:
    """Iterate over subtasks, running architect->implementer->commit->(tester) for each."""
    workspace = _resolve_workspace(workspace_dir, sandbox_dir)
    total = len(subtasks)
    constraints = (task_metadata or {}).get("constraints") or {}
    results: list[SubtaskResult] = []

    for i, subtask in enumerate(subtasks):
        run_tester = _should_run_tester(constraints, i, total)
        result = _run_subtask(
            task=task,
            design=design,
            subtask=subtask,
            subtask_index=i,
            total=total,
            workspace=workspace,
            sandbox_dir=sandbox_dir,
            max_retries=max_retries,
            run_tester=run_tester,
            on_status=on_status,
            task_metadata=task_metadata,
        )
        results.append(result)
        _emit(on_status, "subtask_finished", subtask["id"], total, None,
              f"subtask {subtask['id']}/{total} {result.status}")

    return results
