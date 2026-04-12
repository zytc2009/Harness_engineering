"""Unified execution layer for provider- and CLI-backed phase calls."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import config


def _constraints(task_metadata: dict | None) -> dict[str, str]:
    raw = (task_metadata or {}).get("constraints") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key).lower(): str(value) for key, value in raw.items() if value is not None}


def _phase_constraint(constraints: dict[str, str], phase: str, key: str) -> str:
    return constraints.get(f"{phase.lower()}_{key}", "").strip()


def _constraint_or_env(
    constraints: dict[str, str],
    phase: str,
    key: str,
    phase_env_key: str,
    global_env_key: str | None = None,
) -> str:
    phase_value = _phase_constraint(constraints, phase, key)
    if phase_value:
        return phase_value
    global_value = constraints.get(key, "").strip()
    if global_value:
        return global_value
    phase_env = config.get_setting(f"{phase.upper()}_{phase_env_key}", "").strip()
    if phase_env:
        return phase_env
    return config.get_setting(global_env_key or phase_env_key, "").strip()


def resolve_phase_execution(phase: str, task_metadata: dict | None = None) -> dict[str, str | int]:
    constraints = _constraints(task_metadata)
    mode = _constraint_or_env(constraints, phase, "execution_mode", "EXECUTION_MODE").lower() or "provider"
    if mode not in {"provider", "cli"}:
        raise ValueError(f"Unsupported execution_mode for phase '{phase}': {mode}")

    if mode == "cli":
        command = _constraint_or_env(constraints, phase, "cli_command", "CLI_COMMAND")
        timeout_raw = _constraint_or_env(constraints, phase, "cli_timeout", "CLI_TIMEOUT") or "180"
        try:
            timeout = int(timeout_raw)
        except ValueError as exc:
            raise ValueError(f"Invalid CLI timeout for phase '{phase}': {timeout_raw}") from exc
        return {
            "mode": "cli",
            "command": command,
            "timeout": timeout,
        }

    provider = _constraint_or_env(constraints, phase, "provider", "PROVIDER").lower()
    if not provider:
        provider = config._resolve_provider(phase)
    model = _constraint_or_env(constraints, phase, "model", "MODEL", "MAIN_MODEL")
    if not model:
        model = config._resolve_model(phase)
    api_key = _constraint_or_env(constraints, phase, "api_key", "API_KEY")
    if not api_key:
        api_key = config._resolve_api_key(provider, phase)
    base_url = _constraint_or_env(constraints, phase, "base_url", "BASE_URL", "OPENAI_COMPATIBLE_BASE_URL")
    if not base_url and provider != "anthropic":
        base_url = config._resolve_base_url(provider, phase)
    user_agent = _constraint_or_env(constraints, phase, "user_agent", "USER_AGENT")
    return {
        "mode": "provider",
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "user_agent": user_agent,
    }


def describe_phase_execution(phase: str, task_metadata: dict | None = None) -> str:
    resolved = resolve_phase_execution(phase, task_metadata=task_metadata)
    if resolved["mode"] == "cli":
        command = str(resolved["command"]).strip()
        preview = command[:60] + "..." if len(command) > 60 else command
        return f"cli / {preview}"
    return f"provider / {resolved['provider']} / {resolved['model']}"


def _validate_cli_command(command: str, phase: str) -> None:
    if not command.strip():
        raise EnvironmentError(f"{phase.upper()} uses cli mode but no CLI command is configured.")
    has_prompt = "{prompt_file}" in command or "{prompt_content}" in command
    has_stdin = command.rstrip().endswith(" -") or " - " in command
    if not has_prompt and not has_stdin:
        raise EnvironmentError(
            f"{phase.upper()} CLI command must accept prompt input via {{prompt_file}}, {{prompt_content}}, or stdin '-'."
        )


def validate_phase_execution(phase: str, task_metadata: dict | None = None) -> None:
    resolved = resolve_phase_execution(phase, task_metadata=task_metadata)
    if resolved["mode"] == "cli":
        _validate_cli_command(str(resolved["command"]), phase)
        return

    provider = str(resolved["provider"])
    api_key = str(resolved["api_key"])
    if provider == "anthropic":
        if not api_key:
            raise EnvironmentError(
                f"\n{phase.upper()} uses provider=anthropic but no API key found.\n"
                f"Set {phase.upper()}_API_KEY or ANTHROPIC_API_KEY in .env\n"
            )
    elif provider != "ollama" and not api_key:
        raise EnvironmentError(
            f"\n{phase.upper()} uses provider={provider} but no API key found.\n"
            f"Set {phase.upper()}_API_KEY or OPENAI_COMPATIBLE_API_KEY in .env\n"
        )


def validate_runtime(task_metadata: dict | None = None) -> None:
    needs_openai = False
    for phase in ("architect", "implementer", "tester"):
        validate_phase_execution(phase, task_metadata=task_metadata)
        resolved = resolve_phase_execution(phase, task_metadata=task_metadata)
        if resolved["mode"] == "provider" and str(resolved["provider"]) != "anthropic":
            needs_openai = True

    if needs_openai:
        try:
            import langchain_openai  # noqa: F401
        except ImportError:
            raise ImportError(
                "\nlangchain-openai is not installed.\n"
                "Run: pip install langchain-openai\n"
            )


def _messages_to_prompt(messages: list) -> str:
    parts: list[str] = []
    for message in messages:
        role = type(message).__name__.replace("Message", "")
        parts.append(f"[{role}]\n{message.content}")
    return "\n\n".join(parts).strip()


def _build_subprocess_args(command: str) -> dict:
    if sys.platform == "win32":
        return {
            "args": ["powershell", "-Command", command],
            "shell": False,
        }
    return {"args": command, "shell": True}


def _extract_json_text(output: str) -> str:
    import json

    text_parts: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("content"), list):
            for item in data["content"]:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    text_parts.append(item["text"])
    return "\n".join(text_parts) if text_parts else output


def _invoke_cli(command: str, prompt: str, timeout: int) -> str:
    prompt_file: str | None = None
    output_file: str | None = None
    stdin_input: str | None = None
    expanded = command
    try:
        if "{prompt_file}" in expanded:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as handle:
                handle.write(prompt)
                prompt_file = handle.name
            if sys.platform == "win32":
                prompt_file = Path(prompt_file).as_posix()
            expanded = expanded.replace("{prompt_file}", prompt_file)
        elif "{prompt_content}" in expanded:
            expanded = expanded.replace("{prompt_content}", prompt)
        else:
            stdin_input = prompt

        if "{output_file}" in expanded:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as handle:
                output_file = handle.name
            if sys.platform == "win32":
                output_file = Path(output_file).as_posix()
            expanded = expanded.replace("{output_file}", output_file)

        result = subprocess.run(
            **_build_subprocess_args(expanded),
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if output_file and Path(output_file).exists():
            output = Path(output_file).read_text(encoding="utf-8")
        else:
            output = result.stdout.strip()
        output = _extract_json_text(output).strip()
        if result.returncode != 0:
            error = result.stderr.strip() or output or f"CLI exited with code {result.returncode}"
            raise RuntimeError(error)
        if not output:
            raise RuntimeError("CLI returned empty output")
        return re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
    finally:
        for path in (prompt_file, output_file):
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass


def invoke_phase(phase: str, messages: list, task_metadata: dict | None = None) -> str:
    resolved = resolve_phase_execution(phase, task_metadata=task_metadata)
    if resolved["mode"] == "cli":
        return _invoke_cli(
            command=str(resolved["command"]),
            prompt=_messages_to_prompt(messages),
            timeout=int(resolved["timeout"]),
        )

    llm = config.get_llm(
        phase=phase,
        provider=str(resolved["provider"]),
        model=str(resolved["model"]),
        api_key=str(resolved["api_key"]),
        base_url=str(resolved["base_url"]),
        user_agent=str(resolved["user_agent"]),
    )
    full_content = ""
    in_think = False
    think_chars = 0
    try:
        for chunk in llm.stream(messages):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if not text:
                continue
            full_content += text
            if "<think>" in text and not in_think:
                in_think = True
                print("  [thinking", end="", flush=True)
                think_chars = 0
            if in_think:
                think_chars += len(text)
                if think_chars >= 200:
                    print(".", end="", flush=True)
                    think_chars = 0
                if "</think>" in text:
                    in_think = False
                    think_chars = 0
                    print("]", flush=True)
                continue
            print(text, end="", flush=True)
        print()
        if not full_content:
            response = llm.invoke(messages)
            full_content = response.content if isinstance(response.content, str) else str(response.content)
            print(full_content[:300] + "..." if len(full_content) > 300 else full_content)
    except Exception:
        response = llm.invoke(messages)
        full_content = response.content if isinstance(response.content, str) else str(response.content)
        print(full_content[:300] + "..." if len(full_content) > 300 else full_content)
    return re.sub(r"<think>.*?</think>", "", full_content, flags=re.DOTALL).strip()
