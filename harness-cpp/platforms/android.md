# 平台说明：Android

---

## 环境要求

- **NDK**：r25+（Clang 14+）
- **最低 API**：24（Android 7.0）— `std::filesystem` 需要此版本
- **目标 ABI**：`arm64-v8a`（主要），可选 `armeabi-v7a`、`x86_64`（模拟器）
- **STL**：`c++_shared`（多个 .so 共享同一份 STL）
- **vcpkg triplet**：`arm64-android`
- **构建方式**：CMake（通过 NDK 提供的工具链，或 Gradle + CMake 集成）

---

## 关键差异

### JNI 桥接
Android 应用通过 JNI 调用 C++ 代码：
```cpp
// src/platform/android/jni/my_module_jni.cpp
#include <jni.h>
#include "core/my_module.h"

extern "C" JNIEXPORT jstring JNICALL
Java_com_example_MyModule_process(JNIEnv* env, jobject /* this */, jstring input) {
    // 1. Java string → C++ string
    const char* input_cstr = env->GetStringUTFChars(input, nullptr);
    std::string input_str(input_cstr);
    env->ReleaseStringUTFChars(input, input_cstr);

    // 2. 调用 C++ 核心逻辑
    auto result = my_module::process(input_str);

    // 3. 处理错误（C++ 异常不能跨 JNI 边界！）
    if (!result) {
        env->ThrowNew(
            env->FindClass("java/lang/RuntimeException"),
            result.error().message.c_str()
        );
        return nullptr;
    }

    // 4. C++ string → Java string
    return env->NewStringUTF(result.value().c_str());
}
```

**JNI 规则**：
- JNI 层必须是薄层——只做类型转换，不做业务逻辑
- C++ 异常必须在 JNI 层 catch，转为 `env->ThrowNew()`
- JNI 本地引用有限（默认 512 个），大批量操作用 `PushLocalFrame` / `PopLocalFrame`
- `GetStringUTFChars` 返回的是 Modified UTF-8，不是标准 UTF-8（大多数场景无影响）

### STL 选择
```cmake
# 在工具链文件或 CMakePresets 中设置
set(ANDROID_STL c++_shared)  # 不要用 c++_static
```
原因：如果多个 .so 各自静态链接 STL，会有多份 STL 实例，导致跨库传递 `std::string` 等类型时 ODR 违规和崩溃。

### 文件系统
Android 应用沙箱严格限制文件访问：
```
内部存储（无需权限）：Context.getFilesDir()    → /data/data/<package>/files/
缓存目录：              Context.getCacheDir()    → /data/data/<package>/cache/
外部存储（需权限）：    Context.getExternalFilesDir()
```
C++ 层通过 JNI 获取这些路径，不要硬编码。

### 日志
```cpp
#include <android/log.h>
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "MyApp", __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, "MyApp", __VA_ARGS__)
```

---

## CMake 配置

### 工具链文件
使用 NDK 自带的工具链：
```cmake
# cmake/toolchains/android.toolchain.cmake
# 通常直接用 NDK 提供的：$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake
# 自定义工具链用于覆盖特定设置

set(CMAKE_SYSTEM_NAME Android)
set(CMAKE_ANDROID_NDK $ENV{ANDROID_NDK_HOME})
set(CMAKE_ANDROID_API 24)
set(CMAKE_ANDROID_ARCH_ABI arm64-v8a)
set(CMAKE_ANDROID_STL_TYPE c++_shared)
```

### CMake 预设片段

```json
{
    "name": "android-debug",
    "inherits": "base",
    "cacheVariables": {
        "CMAKE_SYSTEM_NAME": "Android",
        "CMAKE_ANDROID_NDK": "$env{ANDROID_NDK_HOME}",
        "CMAKE_ANDROID_API": "24",
        "CMAKE_ANDROID_ARCH_ABI": "arm64-v8a",
        "CMAKE_ANDROID_STL_TYPE": "c++_shared",
        "CMAKE_BUILD_TYPE": "Debug",
        "VCPKG_TARGET_TRIPLET": "arm64-android"
    }
}
```

---

## 测试

Android 上运行 Google Test 有两种方式：

1. **adb push + shell 执行**（快速但有限）：
```bash
adb push build/android-debug/tests/my_test /data/local/tmp/
adb shell /data/local/tmp/my_test
```

2. **Android Instrumentation Test**（完整但慢）：
通过 Gradle 集成，将 C++ 测试包装为 Android 测试。

开发阶段推荐方式 1。CI 推荐方式 2。

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `UnsatisfiedLinkError` | .so 未打包或 ABI 不匹配 | 检查 CMake ABI 配置 + Gradle 的 abiFilters |
| STL 类型跨 .so 崩溃 | 使用了 `c++_static` | 改为 `c++_shared` |
| `std::filesystem` 不可用 | API level < 24 | 确认 `CMAKE_ANDROID_API >= 24` |
| JNI 崩溃无堆栈 | C++ 异常跨了 JNI 边界 | JNI 层必须 catch 所有 C++ 异常 |
| 权限拒绝访问文件 | 访问了沙箱外路径 | 通过 JNI 获取 Context 提供的路径 |
