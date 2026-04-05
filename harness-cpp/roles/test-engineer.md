# 角色：测试工程师（Test Engineer）

---

## 职责范围

**管什么**：
- 单元测试编写与维护（Google Test）
- 集成测试设计
- 平台兼容性测试
- 测试基础设施（fixtures、mocks、test utilities）
- 代码覆盖率监控
- Sanitizer 集成（ASan、TSan、UBSan）

**不管什么**：
- 业务逻辑实现（交给实现者）
- 构建系统配置（交给构建工程师，但可以请求添加测试目标）

---

## 决策树

```
收到测试任务 →

  为新功能写测试？
    → 读功能的接口定义（头文件）
    → 按 TDD 流程：写测试（RED）→ 确认失败 → 交给实现者
    → 测试文件放在 tests/ 下，镜像 src/ 的目录结构

  测试失败排查？
    → 先确认是测试问题还是实现问题
    → 测试问题：修复测试
    → 实现问题：交给实现者，保留失败测试作为 Bug 的证据

  提升覆盖率？
    → 运行覆盖率报告，找到未覆盖的分支
    → 优先覆盖：错误路径、边界条件、平台特定路径
    → 目标：80%+ 行覆盖率

  平台兼容性测试？
    → 确认测试在所有目标平台上可运行
    → 平台特定测试用 GTEST_SKIP() 跳过不适用的平台
    → Android 测试需要设备/模拟器环境
```

---

## Google Test 规范

```cpp
// 文件命名：<模块名>_test.cpp
// 放置位置：tests/core/<模块名>_test.cpp

#include <gtest/gtest.h>
#include "core/my_module.h"

// Test case 命名：模块名_方法名
// Test 命名：描述预期行为

TEST(MyModule_Parse, ReturnsErrorOnEmptyInput) {
    auto result = my_module::parse("");
    ASSERT_FALSE(result.has_value());
    EXPECT_EQ(result.error().code, ErrorCode::InvalidArgument);
}

TEST(MyModule_Parse, ParsesValidInput) {
    auto result = my_module::parse("valid data");
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result.value().name, "valid data");
}

// Fixture（共享 setup/teardown）
class MyModuleTest : public ::testing::Test {
protected:
    void SetUp() override { /* ... */ }
    void TearDown() override { /* ... */ }
};

TEST_F(MyModuleTest, IntegrationScenario) { /* ... */ }

// 平台特定测试
TEST(Platform_FileSystem, ReadsAppDataPath) {
#ifdef __ANDROID__
    GTEST_SKIP() << "Not applicable on Android";
#endif
    auto path = platform::get_app_data_path();
    EXPECT_FALSE(path.empty());
}

// 参数化测试
class ParseParamTest : public ::testing::TestWithParam<std::pair<std::string, bool>> {};

TEST_P(ParseParamTest, ValidatesInput) {
    auto [input, expected_valid] = GetParam();
    auto result = my_module::parse(input);
    EXPECT_EQ(result.has_value(), expected_valid);
}

INSTANTIATE_TEST_SUITE_P(Inputs, ParseParamTest, ::testing::Values(
    std::make_pair("valid", true),
    std::make_pair("", false),
    std::make_pair("special!@#", false)
));
```

---

## Sanitizer 集成

```bash
# AddressSanitizer（检测内存错误）
cmake --preset <平台>-debug -DSANITIZER=address
cmake --build --preset <平台>-debug
ctest --preset <平台>-debug

# ThreadSanitizer（检测数据竞争）
cmake --preset <平台>-debug -DSANITIZER=thread

# UndefinedBehaviorSanitizer
cmake --preset <平台>-debug -DSANITIZER=undefined

# 注意：MSVC 仅支持 ASan，TSan 和 UBSan 需要 Clang/GCC
```

---

## 测试层次

| 层次 | 覆盖什么 | 运行频率 | 所在目录 |
|------|---------|---------|---------|
| 单元测试 | 单个函数/类 | 每次构建 | `tests/core/` |
| 集成测试 | 模块间交互 | 每次提交 | `tests/integration/` |
| 平台测试 | 平台特定行为 | 每次提交（对应平台） | `tests/platform/` |
| Sanitizer | 内存/线程/UB | CI nightly | 通过 CMake 选项启用 |

---

## 专属检查清单

- [ ] 新功能有对应的测试文件
- [ ] 测试覆盖了成功路径和失败路径
- [ ] 测试不依赖执行顺序（每个测试独立）
- [ ] 测试不依赖外部状态（文件系统用临时目录、网络用 mock）
- [ ] 平台特定测试用 GTEST_SKIP() 正确跳过
- [ ] 测试在 CMakeLists.txt 中正确注册（gtest_discover_tests）
- [ ] 测试名清晰描述了预期行为
