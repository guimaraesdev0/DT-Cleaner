---
name: False positive
about: DT-Cleaner offered something it should not have
title: "[FP] "
labels: false-positive, safety
---

**What was offered**

The folder name, and its risk level and confidence as shown in the app.

**Path shape** (please do not paste a real path from a machine you care about)

```
<project>/<something>/build
```

**What was actually in it**

**What project markers were nearby**

Anything from `package.json`, `Cargo.toml`, `pyproject.toml`, `*.csproj`,
`pom.xml`, `build.gradle` in the folder or its parents.

**Details screen**

Press `D` on the item and paste the "Why it was detected" line.

**Environment**

Output of `dtc doctor`.
