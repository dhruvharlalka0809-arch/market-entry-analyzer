import subprocess
import sys


COMMANDS = [
    [sys.executable, "-m", "py_compile", "app.py", "pipeline.py", "prompts.py", "tests/test_adversarial.py", "tests/test_report_parsing.py"],
    [sys.executable, "-m", "pytest", "-q"],
]


def main() -> int:
    for command in COMMANDS:
        print("+", " ".join(command))
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
