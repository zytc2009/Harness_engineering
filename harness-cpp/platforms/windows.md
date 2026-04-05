# 平台说明：Windows

---

## 环境要求

- **编译器**：MSVC 19.30+（Visual Studio 2022+）
- **生成器**：Ninja（推荐）或 Visual Studio 17 2022
- **Windows SDK**：10.0.19041.0+
- **vcpkg triplet**：`x64-windows`（动态库）或 `x64-windows-static`

---

## 关键差异

### Unicode
Windows 原生使用 UTF-16（`wchar_t`）。所有与 Win32 API 交互的地方需要 UTF-8 ↔ UTF-16 转换：
```cpp
// 推荐：封装转换函数在平台层
auto to_wide(std::string_view utf8) -> std::wstring;
auto to_utf8(std::wstring_view wide) -> std::string;

// 调用 Win32 API 时：
auto path = to_wide(utf8_path);
auto handle = CreateFileW(path.c_str(), ...);
```

### DLL 导出
MSVC 默认不导出任何符号。必须显式导出：
```cpp
// 使用 CMake GenerateExportHeader 自动生成
#include "mylib_export.h"
class MYLIB_EXPORT MyClass { ... };
```

### 路径长度
Windows 默认最大路径 260 字符。启用长路径支持：
```cmake
# 对于 Windows 10+，在应用 manifest 中启用长路径
```

### MSVC 特有的坑
- `/Zc:__cplusplus` 必须开启，否则 `__cplusplus` 宏报告的值是 199711L
- two-phase lookup 不如 Clang 严格，模板代码需要在 Clang 上也验证
- `#pragma warning(push/pop)` 管理第三方库的警告

---

## CMake 预设片段

```json
{
    "name": "windows-debug",
    "inherits": "base",
    "condition": { "type": "equals", "lhs": "${hostSystemName}", "rhs": "Windows" },
    "generator": "Ninja",
    "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "VCPKG_TARGET_TRIPLET": "x64-windows"
    }
}
```

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| LNK2019 未解析的外部符号 | 缺少导出宏或 target_link_libraries | 检查导出宏 + CMake 链接 |
| C4996 deprecated 警告 | 使用了 MSVC 标记为 deprecated 的函数 | 用安全替代函数或 `_CRT_SECURE_NO_WARNINGS` |
| `__cplusplus` 值不对 | MSVC 默认行为 | 添加 `/Zc:__cplusplus` |
| 中文路径乱码 | UTF-8 / UTF-16 混用 | 统一用 `W` 后缀 API + 转换函数 |
