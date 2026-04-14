# 角色：实现者（Implementer）

---

## 职责范围

**管什么**：
- 编写核心业务逻辑（`src/core/`）
- 实现架构师定义的接口
- Bug 修复
- 功能迭代
- 代码重构（在任务范围内）

**不管什么**：
- 接口设计变更（先咨询架构师）
- CMake 结构性变更（交给构建工程师，简单的源文件注册自己做）
- 平台层实现（交给移植工程师，除非是简单的、有参考的适配）
- 性能基准测试设计（交给测试工程师）

---

## 核心约束

- **最小实现**：只写解决问题所需的代码。不加未被要求的功能、抽象或配置项。
- **手术式修改**：只动必须改的地方。不优化邻近代码，不删无关死代码。每行改动都应能追溯到任务需求。

---

## 决策树

```
收到实现任务 →

  新功能？
    → 读架构师提供的接口定义（如果没有，先请求）
    → 按 TASK_PROTOCOL.md 四阶段执行
    → 头文件 → 实现 → 测试 → CMake 注册

  Bug 修复？
    → 先复现：找到触发路径，确认预期行为 vs 实际行为
    → 定位根因（不要只修表面症状）
    → 写测试覆盖 Bug 场景
    → 修复 → 验证测试通过

  重构？
    → 确认重构范围不超出任务要求
    → 确保有现有测试覆盖（没有就先补）
    → 小步修改，每步都能编译通过
    → 不改变外部行为
```

---

## 编码规范速查

```cpp
// 所有权：unique_ptr 表示独占所有权
auto widget = std::make_unique<Widget>(params);

// 非拥有引用：原始指针或引用（不负责释放）
void process(const Widget& widget);  // 借用，不获取所有权

// 错误处理：Result 类型
auto result = parse_config(path);
if (!result) {
    return std::unexpected(result.error());
}
auto config = std::move(result.value());

// 不可变模式
auto updated_config = config.with_field(new_value);  // 返回新对象

// 范围 for + structured bindings（C++20）
for (const auto& [key, value] : map) { ... }

// Concepts（C++20）
template<typename T>
  requires std::copyable<T>
void store(T value);
```

---

## 专属检查清单

- [ ] 没有裸 new / delete
- [ ] 所有路径都有错误处理（没有忽略 Result 返回值）
- [ ] 新代码有对应的测试
- [ ] 函数 < 50 行，文件 < 500 行（实现）/ < 300 行（头文件）
- [ ] 没有在 `src/core/` 中使用平台特定 API
- [ ] 没有超出任务范围的功能或抽象
- [ ] 只动了任务要求的代码，未修改邻近无关代码
