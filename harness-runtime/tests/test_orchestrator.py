"""Tests for the one-shot pipeline orchestrator."""

import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure harness-runtime is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator import _parse_files, architect_phase, implementer_phase
from orchestrator import tester_phase as _tester_phase
from orchestrator import run_pipeline


# ── _parse_files ───────────────────────────────────────────────────

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
        result = _parse_files(text)
        assert result == {"a.py": "x = 1", "b.py": "y = 2"}

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
        result = _parse_files(text)
        assert result == {"README.md": "# Title"}


# ── architect_phase ────────────────────────────────────────────────

class TestArchitectPhase:
    def _make_llm_response(self, content: str):
        mock_response = MagicMock()
        mock_response.content = content
        return mock_response

    def test_writes_design_md(self, tmp_path):
        design_text = "# My Design\nModules: foo, bar"
        with (
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
            patch("builtins.input", return_value="yes"),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = self._make_llm_response(design_text)
            mock_get_llm.return_value = mock_llm

            result = architect_phase("build a calculator")

        assert (tmp_path / "design.md").exists()
        assert result == design_text

    def test_extracts_markdown_block(self, tmp_path):
        response = "Here is the design:\n```markdown\n# Design\ncontent\n```\nDESIGN COMPLETE"
        with (
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
            patch("builtins.input", return_value="yes"),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = self._make_llm_response(response)
            mock_get_llm.return_value = mock_llm

            result = architect_phase("build something")

        assert result == "# Design\ncontent"

    def test_returns_none_when_cancelled(self, tmp_path):
        with (
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
            patch("builtins.input", return_value="no"),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = self._make_llm_response("design text")
            mock_get_llm.return_value = mock_llm

            result = architect_phase("build something")

        assert result is None


# ── implementer_phase ──────────────────────────────────────────────

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
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = MagicMock(content=response)
            mock_get_llm.return_value = mock_llm

            files = implementer_phase("build x", "design text")

        assert "errors.py" in files
        assert "main.py" in files
        assert (tmp_path / "errors.py").read_text() == "class Err(Exception): pass"

    def test_includes_feedback_in_prompt(self, tmp_path):
        with (
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = MagicMock(content="## FILE: x.py\n```python\nx=1\n```")
            mock_get_llm.return_value = mock_llm

            implementer_phase("task", "design", feedback="test failed: AssertionError")

        call_args = mock_llm.invoke.call_args[0][0]
        human_content = call_args[-1].content
        assert "AssertionError" in human_content

    def test_returns_empty_dict_on_no_parse(self, tmp_path):
        with (
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = MagicMock(content="Here is some text with no file blocks.")
            mock_get_llm.return_value = mock_llm

            files = implementer_phase("task", "design")

        assert files == {}


# ── tester_phase ───────────────────────────────────────────────────

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
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = MagicMock(content=response)
            mock_get_llm.return_value = mock_llm

            passed, report = _tester_phase("task", "design", {"main.py": "x=1"})

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
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = MagicMock(content=response)
            mock_get_llm.return_value = mock_llm

            passed, _ = _tester_phase("task", "design", {"main.py": "x=1"})

        assert passed is False

    def test_text_verdict_fallback(self, tmp_path):
        with (
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = MagicMock(content="ALL TESTS PASSED. Everything looks good.")
            mock_get_llm.return_value = mock_llm

            passed, _ = _tester_phase("task", "design", {"main.py": "x=1"})

        assert passed is True

    def test_text_verdict_fail_fallback(self, tmp_path):
        with (
            patch("orchestrator.config.get_llm") as mock_get_llm,
            patch("orchestrator.SANDBOX", tmp_path),
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = MagicMock(content="TESTS FAILED: something is wrong.")
            mock_get_llm.return_value = mock_llm

            passed, _ = _tester_phase("task", "design", {"main.py": "x=1"})

        assert passed is False


# ── run_pipeline ───────────────────────────────────────────────────

class TestRunPipeline:
    def _patch_phases(self, design="design", impl_files=None, test_passed=True):
        """Patch all three phases for pipeline integration tests."""
        impl_files = impl_files or {"main.py": "x=1"}
        return (
            patch("orchestrator.architect_phase", return_value=design),
            patch("orchestrator.implementer_phase", return_value=impl_files),
            patch("orchestrator.tester_phase", return_value=(test_passed, "report")),
        )

    def test_pipeline_passes_on_first_try(self):
        with (
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
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", return_value=(False, "always fails")),
        ):
            result = run_pipeline("build something", max_retries=2)

        assert result["phase"] == "done"
        assert result.get("failed") is True
        assert result["retry_count"] == 2

    def test_pipeline_cancelled_by_user(self):
        with patch("orchestrator.architect_phase", return_value=None):
            result = run_pipeline("build something")

        assert result["phase"] == "cancelled"

    def test_feedback_passed_to_implementer_on_retry(self):
        feedback_report = "AssertionError on line 5"
        with (
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}) as mock_impl,
            patch("orchestrator.tester_phase", side_effect=[
                (False, feedback_report), (True, "pass"),
            ]),
        ):
            run_pipeline("build something", max_retries=3)

        # Second call to implementer should include the feedback
        second_call_kwargs = mock_impl.call_args_list[1][1]
        assert feedback_report in second_call_kwargs.get("feedback", "")
