"""JVM (Maven / Gradle / sbt) artifacts.

`target` is shared with Rust and `build` with half the world, so both rely on
JVM markers (`pom.xml`, `build.gradle`, `gradlew`, ...) being proven nearby.

The project-local `.gradle` folder is included; the GLOBAL Gradle cache
(`~/.gradle/caches`) is handled separately in `gradle_cache` because it is
shared across every project on the machine and re-downloading it costs real
bandwidth -- hence MEDIUM risk and no auto-selection.
"""

from __future__ import annotations

from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.detectors.base import Rule, RuleDetector, register


class JvmDetector(RuleDetector):
    name = "jvm"
    ecosystem = Ecosystem.JVM
    rules = (
        Rule(
            name="target",
            category=Category.JVM_BUILD,
            item_type="maven_target",
            risk=RiskLevel.LOW,
            base_confidence=0.5,
            regenerate_hint="mvn package",
        ),
        Rule(
            name="build",
            category=Category.JVM_BUILD,
            item_type="gradle_build",
            risk=RiskLevel.LOW,
            base_confidence=0.5,
            regenerate_hint="gradlew build",
        ),
        Rule(
            name="out",
            category=Category.JVM_BUILD,
            item_type="jvm_out",
            risk=RiskLevel.MEDIUM,
            base_confidence=0.45,
            regenerate_hint="rebuild from your IDE or build tool",
        ),
        Rule(
            name=".gradle",
            category=Category.GRADLE_CACHE,
            item_type="gradle_project_cache",
            risk=RiskLevel.LOW,
            base_confidence=0.8,
            regenerate_hint="gradlew build (re-syncs the project)",
        ),
    )


register(JvmDetector())
