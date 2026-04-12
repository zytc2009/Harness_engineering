"""Tests for the one-shot pipeline orchestrator."""

import logging
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator import _parse_files, architect_phase, implementer_phase
from orchestrator import tester_phase as _tester_phase
from orchestrator import run_pipeline


class TestParseFiles:
    def test_parses_single_file(self):
        text = "## FILE: errors.py\n```python\nclass Err(Exception): pass\n```"
        assert _parse_files(text) == {"errors.py": "class Err(Exception): pass"}

    def test_parses_multiple_files(self):
        text = textwrap.dedent("""\
            ## FILE: a.py
            ```python
            x = 1
            ```

            ## FILE: b.py
            ```python
            y = 2
            ```
        """)
        assert _parse_files(text) == {"a.py": "x = 1", "b.py": "y = 2"}

    def test_strips_path_prefix(self):
        text = "## FILE: src/utils/helper.py\n```python\ndef f(): pass\n```"
        result = _parse_files(text)
        assert "helper.py" in result

    def test_returns_empty_when_no_blocks(self):
        assert _parse_files("No file blocks here.") == {}

    def test_ignores_content_outside_blocks(self):
        text = textwrap.dedent("""\
            Here is my implementation:

            ## FILE: main.py
            ```python
            print("hello")
            ```

            Let me know if you need changes.
        """)
        assert _parse_files(text) == {"main.py": 'print("hello")'}

    def test_handles_non_python_blocks(self):
        text = "## FILE: README.md\n```markdown\n# Title\n```"
        assert _parse_files(text) == {"README.md": "# Title"}


class TestArchitectPhase:
    def test_writes_design_md(self, tmp_path):
        design_text = "# My Design\nModules: foo, bar"
        with (
            patch("orchestrator.execution.invoke_phase", return_value=design_text),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            result = architect_phase("build a calculator")

        assert (tmp_path / "design.md").exists()
        assert result == design_text

    def test_extracts_markdown_block(self, tmp_path):
        response = "Here is the design:\n```markdown\n# Design\ncontent\n```\nDESIGN COMPLETE"
        with (
            patch("orchestrator.execution.invoke_phase", return_value=response),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            result = architect_phase("build something")

        assert result == "# Design\ncontent"

    def test_respects_explicit_sandbox_dir(self, tmp_path):
        sandbox_dir = tmp_path / "task-123"
        with patch("orchestrator.execution.invoke_phase", return_value="design text"):
            result = architect_phase("build something", sandbox_dir=sandbox_dir)

        assert result == "design text"
        assert (sandbox_dir / "design.md").read_text() == "design text"


class TestImplementerPhase:
    def test_writes_all_parsed_files(self, tmp_path):
        response = textwrap.dedent("""\
            ## FILE: errors.py
            ```python
            class Err(Exception): pass
            ```
            ## FILE: main.py
            ```python
            print("hi")
            ```
        """)
        with (
            patch("orchestrator.execution.invoke_phase", return_value=response),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            files = implementer_phase("build x", "design text")

        assert "errors.py" in files
        assert "main.py" in files
        assert (tmp_path / "errors.py").read_text() == "class Err(Exception): pass"

    def test_includes_feedback_in_prompt(self, tmp_path):
        with (
            patch("orchestrator.execution.invoke_phase", return_value="## FILE: x.py\n```python\nx=1\n```") as mock_invoke,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            implementer_phase("task", "design", feedback="test failed: AssertionError")

        call_args = mock_invoke.call_args[0][1]
        human_content = call_args[-1].content
        assert "AssertionError" in human_content

    def test_returns_empty_dict_on_no_parse(self, tmp_path):
        with (
            patch("orchestrator.execution.invoke_phase", return_value="Here is some text with no file blocks."),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            files = implementer_phase("task", "design")

        assert files == {}


class TestTesterPhase:
    def test_executes_generated_test_file(self, tmp_path):
        passing_test = textwrap.dedent("""\
            import unittest
            class T(unittest.TestCase):
                def test_pass(self): self.assertTrue(True)
            if __name__ == "__main__": unittest.main()
        """)
        response = f"## FILE: test_impl.py\n```python\n{passing_test}\n```"
        with (
            patch("orchestrator.execution.invoke_phase", return_value=response),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            passed, _report = _tester_phase("task", "design", {"main.py": "x=1"})

        assert passed is True

    def test_returns_false_on_failing_tests(self, tmp_path):
        failing_test = textwrap.dedent("""\
            import unittest
            class T(unittest.TestCase):
                def test_fail(self): self.fail("intentional")
            if __name__ == "__main__": unittest.main()
        """)
        response = f"## FILE: test_impl.py\n```python\n{failing_test}\n```"
        with (
            patch("orchestrator.execution.invoke_phase", return_value=response),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            passed, _ = _tester_phase("task", "design", {"main.py": "x=1"})

        assert passed is False

    def test_text_verdict_fallback(self, tmp_path):
        with (
            patch("orchestrator.execution.invoke_phase", return_value="ALL TESTS PASSED. Everything looks good."),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            passed, _ = _tester_phase("task", "design", {"main.py": "x=1"})

        assert passed is True

    def test_text_verdict_fail_fallback(self, tmp_path):
        with (
            patch("orchestrator.execution.invoke_phase", return_value="TESTS FAILED: something is wrong."),
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            passed, _ = _tester_phase("task", "design", {"main.py": "x=1"})

        assert passed is False


class TestRunPipeline:
    def test_pipeline_passes_on_first_try(self):
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design") as mock_arch,
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}) as mock_impl,
            patch("orchestrator.tester_phase", return_value=(True, "ok")) as mock_test,
        ):
            result = run_pipeline("build something", max_retries=3)

        assert result["phase"] == "done"
        assert result["retry_count"] == 0
        mock_arch.assert_called_once()
        mock_impl.assert_called_once()
        mock_test.assert_called_once()

    def test_pipeline_retries_on_failure(self):
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", side_effect=[
                (False, "fail"), (True, "pass"),
            ]) as mock_test,
        ):
            result = run_pipeline("build something", max_retries=3)

        assert result["phase"] == "done"
        assert result["retry_count"] == 1
        assert mock_test.call_count == 2

    def test_pipeline_stops_after_max_retries(self):
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", return_value=(False, "always fails")),
        ):
            result = run_pipeline("build something", max_retries=2)

        assert result["phase"] == "done"
        assert result.get("failed") is True
        assert result["retry_count"] == 2

    def test_pipeline_retries_when_implementer_outputs_no_files(self):
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", side_effect=[{}, {"main.py": "x"}]) as mock_impl,
            patch("orchestrator.tester_phase", return_value=(True, "ok")) as mock_test,
        ):
            result = run_pipeline("build something", max_retries=3)

        assert result["phase"] == "done"
        assert result["retry_count"] == 1
        assert mock_impl.call_count == 2
        mock_test.assert_called_once()

    def test_pipeline_fails_without_running_tester_when_implementer_never_outputs_files(self):
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={}),
            patch("orchestrator.tester_phase") as mock_test,
        ):
            result = run_pipeline("build something", max_retries=2)

        assert result["phase"] == "done"
        assert result.get("failed") is True
        assert result["retry_count"] == 2
        assert "no parseable `## FILE:` blocks" in result["tester_report"]
        mock_test.assert_not_called()

    def test_pipeline_cancelled_by_user(self):
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value=None),
        ):
            result = run_pipeline("build something")

        assert result["phase"] == "cancelled"

    def test_feedback_passed_to_implementer_on_retry(self):
        feedback_report = "AssertionError on line 5"
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}) as mock_impl,
            patch("orchestrator.tester_phase", side_effect=[
                (False, feedback_report), (True, "pass"),
            ]),
        ):
            run_pipeline("build something", max_retries=3)

        second_call_kwargs = mock_impl.call_args_list[1][1]
        assert feedback_report in second_call_kwargs.get("feedback", "")

    def test_callback_receives_phase_events(self, tmp_path):
        events = []
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", return_value=(True, "ok")),
        ):
            result = run_pipeline(
                "build something",
                max_retries=3,
                sandbox_dir=tmp_path,
                on_status=events.append,
            )

        assert result["phase"] == "done"
        assert [event["type"] for event in events] == [
            "phase_started",
            "phase_finished",
            "phase_started",
            "phase_finished",
            "phase_started",
            "phase_finished",
            "pipeline_done",
        ]
        assert [event["phase"] for event in events[:6]] == [
            "architect",
            "architect",
            "implementer",
            "implementer",
            "tester",
            "tester",
        ]

    def test_callback_includes_retry_event(self, tmp_path):
        events = []
        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", side_effect=[(False, "fail"), (True, "ok")]),
        ):
            result = run_pipeline(
                "build something",
                max_retries=3,
                sandbox_dir=tmp_path,
                on_status=events.append,
            )

        assert result["retry_count"] == 1
        retry_event = next(event for event in events if event["type"] == "retrying")
        assert retry_event["phase"] == "implementer"
        assert retry_event["retry_count"] == 1

    def test_pipeline_uses_provided_sandbox_on_resume(self, tmp_path):
        sandbox_dir = tmp_path / "task-abc"
        sandbox_dir.mkdir()
        (sandbox_dir / "design.md").write_text("design", encoding="utf-8")
        (sandbox_dir / "main.py").write_text("x=1", encoding="utf-8")

        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.implementer_phase") as mock_impl,
            patch("orchestrator.tester_phase", return_value=(True, "ok")),
        ):
            result = run_pipeline(
                "build something",
                start_phase="tester",
                sandbox_dir=sandbox_dir,
            )

        assert result["phase"] == "done"
        mock_impl.assert_not_called()

    def test_pipeline_retries_implementer_after_tester_resume_failure(self, tmp_path):
        sandbox_dir = tmp_path / "task-abc"
        sandbox_dir.mkdir()
        (sandbox_dir / "design.md").write_text("design", encoding="utf-8")
        (sandbox_dir / "main.py").write_text("x=1", encoding="utf-8")

        with (
            patch("orchestrator.execution.validate_runtime"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "fixed"}) as mock_impl,
            patch("orchestrator.tester_phase", side_effect=[(False, "fail"), (True, "ok")]),
        ):
            result = run_pipeline(
                "build something",
                start_phase="tester",
                max_retries=3,
                sandbox_dir=sandbox_dir,
            )

        assert result["phase"] == "done"
        assert result["retry_count"] == 1
        mock_impl.assert_called_once()


class TestReadSandbox:
    def test_logs_when_file_read_fails(self, tmp_path, caplog):
        good = tmp_path / "good.txt"
        bad = tmp_path / "bad.txt"
        good.write_text("ok", encoding="utf-8")
        bad.write_bytes(b"\xff")

        with (
            caplog.at_level(logging.WARNING),
            patch("orchestrator._resolve_sandbox_dir", return_value=tmp_path),
        ):
            from orchestrator import _read_sandbox

            result = _read_sandbox(tmp_path)

        assert result == {"good.txt": "ok"}
        assert f"Failed to read sandbox file {bad}" in caplog.text
