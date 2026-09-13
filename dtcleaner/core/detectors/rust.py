"""Rust artifacts.

`target` is the canonical false-positive trap: the word means something in
plenty of other contexts (Maven output, a `target` asset folder, a build system
directory). It is flagged ambiguous, so it is only ever deletable when a
`Cargo.toml` sits at or above it.

Risk is MEDIUM rather than LOW because a Rust rebuild is genuinely expensive --
a cold `cargo build` on a large workspace can take many minutes and re-download
crates.
"""

from __future__ import annotations

from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.detectors.base import Rule, RuleDetector, register


class RustDetector(RuleDetector):
    name = "rust"
    ecosystem = Ecosystem.RUST
    rules = (
        Rule(
            name="target",
            category=Category.RUST_TARGET,
            item_type="cargo_target",
            risk=RiskLevel.MEDIUM,
            base_confidence=0.5,
            regenerate_hint="cargo build (re-downloads and recompiles crates)",
        ),
    )


register(RustDetector())
