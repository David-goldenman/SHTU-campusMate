# 正式版产物

从 `main` 构建的正式版 IPA 放在这里，文件名固定 `campusMate.ipa`。

```bash
# 只在合并到 main 之后执行
cd ios/local
CAMPUS_RELEASE=1 ./build_local.sh release
# → ios/ipa/campusMate.ipa
```

规则（详见 [../DEVELOPMENT.md](../DEVELOPMENT.md)）：

- 开发期**不构建**正式版；日常使用的 `campusMate-dev.ipa` 留在 `ios/local/`；
- 正式版版本号从 `1.0.0` 起，修 bug 只递增第三位；
- Bundle ID 固定 `edu.shanghaitech.campusmate.local`，不随版本变化；
- IPA 本身不进版本库，本目录只保留这份说明。
