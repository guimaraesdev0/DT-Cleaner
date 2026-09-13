""".NET artifacts.

`bin` and `obj` are the most dangerous names in the whole catalog. `bin` in
particular is a normal folder name in countless unrelated projects (and on
Unix-shaped trees it is where executables live).

Two guards apply here:

* both names are ambiguous, so a `.sln` / `.csproj` / `.fsproj` / `.vbproj`
  must be proven nearby;
* the marker distance is short by design (see MAX_AMBIGUOUS_MARKER_DISTANCE),
  because in .NET the project file sits right next to `bin` and `obj`.
"""

from __future__ import annotations

from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.detectors.base import Rule, RuleDetector, register


class DotNetDetector(RuleDetector):
    name = "dotnet"
    ecosystem = Ecosystem.DOTNET
    rules = (
        Rule(
            name="bin",
            category=Category.DOTNET_BUILD,
            item_type="dotnet_bin",
            risk=RiskLevel.LOW,
            base_confidence=0.45,
            regenerate_hint="dotnet build",
        ),
        Rule(
            name="obj",
            category=Category.DOTNET_BUILD,
            item_type="dotnet_obj",
            risk=RiskLevel.LOW,
            base_confidence=0.5,
            regenerate_hint="dotnet build",
        ),
    )


register(DotNetDetector())
