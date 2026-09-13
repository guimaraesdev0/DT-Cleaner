"""Python artifacts.

`__pycache__` and the tool caches are unambiguous and cheap to regenerate.
`build` and `dist` are shared with every other ecosystem, so they carry low base
confidence and depend entirely on a proven Python project.

Note: virtual environments (`.venv`, `venv`) are deliberately NOT detected.
They are expensive to rebuild, frequently contain pinned or patched packages,
and users treat them as part of the working environment rather than as output.
"""

from __future__ import annotations

from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.detectors.base import Rule, RuleDetector, register


class PythonDetector(RuleDetector):
    name = "python"
    ecosystem = Ecosystem.PYTHON
    rules = (
        Rule(
            name="__pycache__",
            category=Category.PYTHON_CACHE,
            item_type="pycache",
            risk=RiskLevel.LOW,
            base_confidence=0.9,
            regenerate_hint="regenerated automatically on the next run",
        ),
        Rule(
            name=".pytest_cache",
            category=Category.PYTHON_CACHE,
            item_type="pytest_cache",
            risk=RiskLevel.LOW,
            base_confidence=0.9,
            regenerate_hint="pytest",
        ),
        Rule(
            name=".mypy_cache",
            category=Category.PYTHON_CACHE,
            item_type="mypy_cache",
            risk=RiskLevel.LOW,
            base_confidence=0.9,
            regenerate_hint="mypy .",
        ),
        Rule(
            name=".ruff_cache",
            category=Category.PYTHON_CACHE,
            item_type="ruff_cache",
            risk=RiskLevel.LOW,
            base_confidence=0.9,
            regenerate_hint="ruff check .",
        ),
        Rule(
            name=".tox",
            category=Category.PYTHON_CACHE,
            item_type="tox_env",
            risk=RiskLevel.MEDIUM,
            base_confidence=0.8,
            regenerate_hint="tox (re-creates the environments)",
        ),
        Rule(
            name=".ipynb_checkpoints",
            category=Category.PYTHON_CACHE,
            item_type="ipynb_checkpoints",
            risk=RiskLevel.LOW,
            base_confidence=0.85,
            regenerate_hint="recreated by Jupyter",
        ),
        # --- ambiguous names: require a proven Python project ---------------
        Rule(
            name="build",
            category=Category.PYTHON_BUILD,
            item_type="python_build",
            risk=RiskLevel.LOW,
            base_confidence=0.5,
            regenerate_hint="python -m build",
        ),
        Rule(
            name="dist",
            category=Category.PYTHON_BUILD,
            item_type="python_dist",
            risk=RiskLevel.LOW,
            base_confidence=0.5,
            regenerate_hint="python -m build",
        ),
    )

    def inspect(self, dir_path: str, dir_name: str, parent_name: str):
        """Also recognize `*.egg-info`, which has a variable prefix."""
        if dir_name.casefold().endswith(".egg-info"):
            from dtcleaner.core.models import Candidate

            return Candidate(
                path=dir_path,
                name=dir_name,
                category=Category.PYTHON_BUILD,
                ecosystem=Ecosystem.PYTHON,
                item_type="egg_info",
                ambiguous=False,
                detector=self.name,
                base_confidence=0.85,
                regenerate_hint="pip install -e . / python -m build",
            )
        return super().inspect(dir_path, dir_name, parent_name)


register(PythonDetector())
