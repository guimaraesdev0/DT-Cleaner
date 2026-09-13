"""Android / React Native / Expo artifacts.

Android build output is usually the second biggest win after `node_modules`, so
it gets a dedicated detector rather than riding on the JVM one.

The `parent_name` guard matters here: a `build` folder whose parent is `android`
or `app` is almost certainly Gradle output, which justifies higher confidence
than a bare `build` anywhere else in the tree.

`.expo` and `.metro` caches are unambiguous names owned by their tools.
"""

from __future__ import annotations

from dtcleaner.core.constants import Category, Ecosystem, RiskLevel
from dtcleaner.core.detectors.base import Rule, RuleDetector, register


class AndroidDetector(RuleDetector):
    name = "android"
    ecosystem = Ecosystem.ANDROID
    rules = (
        Rule(
            name="build",
            category=Category.ANDROID_BUILD,
            item_type="android_app_build",
            risk=RiskLevel.LOW,
            base_confidence=0.7,
            regenerate_hint="gradlew assembleDebug",
            parent_name="app",
        ),
        Rule(
            name="build",
            category=Category.ANDROID_BUILD,
            item_type="android_root_build",
            risk=RiskLevel.LOW,
            base_confidence=0.7,
            regenerate_hint="gradlew build",
            parent_name="android",
        ),
        Rule(
            name=".cxx",
            category=Category.ANDROID_BUILD,
            item_type="android_cxx",
            risk=RiskLevel.LOW,
            base_confidence=0.8,
            regenerate_hint="rebuilt by the NDK on the next build",
        ),
        Rule(
            name=".expo",
            category=Category.EXPO_METRO,
            item_type="expo_cache",
            risk=RiskLevel.LOW,
            base_confidence=0.85,
            regenerate_hint="npx expo start",
        ),
        Rule(
            name=".expo-shared",
            category=Category.EXPO_METRO,
            item_type="expo_shared",
            risk=RiskLevel.LOW,
            base_confidence=0.8,
            regenerate_hint="npx expo start",
        ),
        Rule(
            name=".metro",
            category=Category.EXPO_METRO,
            item_type="metro_cache",
            risk=RiskLevel.LOW,
            base_confidence=0.85,
            regenerate_hint="rebuilt by the Metro bundler",
        ),
        Rule(
            name=".metro-cache",
            category=Category.EXPO_METRO,
            item_type="metro_cache_dir",
            risk=RiskLevel.LOW,
            base_confidence=0.85,
            regenerate_hint="rebuilt by the Metro bundler",
        ),
    )


register(AndroidDetector())
