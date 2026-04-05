# 平台说明：macOS

---

## 环境要求

- **编译器**：Apple Clang 14+（Xcode 14+）
- **生成器**：Ninja（推荐）或 Xcode
- **macOS SDK**：13.0+
- **vcpkg triplet**：`arm64-osx`（Apple Silicon）或 `x64-osx`（Intel）
- **Universal Binary**：`CMAKE_OSX_ARCHITECTURES="x86_64;arm64"`（同时支持两架构）

---

## 关键差异

### Objective-C++ 混编
需要调用 Cocoa / AppKit / Foundation API 时，使用 `.mm` 文件：
```cpp
// src/platform/macos/file_dialog.mm
#import <AppKit/AppKit.h>
#include "platform/macos/file_dialog.h"

auto show_file_dialog() -> std::optional<std::filesystem::path> {
    @autoreleasepool {
        NSOpenPanel* panel = [NSOpenPanel openPanel];
        if ([panel runModal] == NSModalResponseOK) {
            return std::filesystem::path([[panel URL] fileSystemRepresentation]);
        }
        return std::nullopt;
    }
}
```

**规则**：
- Objective-C 对象由 ARC 管理，C++ 对象由 RAII 管理，不混用
- `@autoreleasepool` 包裹所有 Obj-C 调用
- `.mm` 文件仅在 `src/platform/macos/` 中出现

### Framework 链接
```cmake
if(APPLE AND NOT ANDROID)
    target_link_libraries(platform PRIVATE
        "-framework Foundation"
        "-framework AppKit"
    )
endif()
```

### Code Signing & Notarization
发布版本需要签名。开发阶段可忽略，但 CI 构建需配置：
```cmake
set(CMAKE_XCODE_ATTRIBUTE_CODE_SIGN_IDENTITY "-")  # Ad-hoc signing for dev
```

### Rpath
macOS 动态库需要正确设置 rpath：
```cmake
set(CMAKE_MACOSX_RPATH ON)
set(CMAKE_INSTALL_RPATH "@executable_path/../lib")
```

---

## CMake 预设片段

```json
{
    "name": "macos-debug",
    "inherits": "base",
    "condition": { "type": "equals", "lhs": "${hostSystemName}", "rhs": "Darwin" },
    "generator": "Ninja",
    "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "VCPKG_TARGET_TRIPLET": "arm64-osx"
    }
}
```

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `ld: symbol not found` | Framework 未链接 | `target_link_libraries(... "-framework Xxx")` |
| ARC 和 C++ 析构冲突 | .mm 中混用 ARC 和 RAII | 分离 Obj-C 和 C++ 对象生命周期 |
| Universal Binary 链接失败 | 某依赖只有单架构 | 确认 vcpkg triplet 或自行编译双架构 |
| `dyld: Library not loaded` | rpath 不对 | 设置 `CMAKE_INSTALL_RPATH` |
