# 机械化检查规则

> 文档会腐烂，lint 规则不会。
> 每条规则包含：检查方法 + 错误信息 + **修复指令**（agent 可直接执行）。
>
> 在中央层面强制执行边界，在本地层面允许自主权。

---

## 使用方式

sub-agent 在 IMPLEMENT → TEST 之后、REVIEW 之前运行这些检查。
集成验证（S7）时由调度器对全部改动文件再跑一遍。

**任何 CRITICAL 检查失败 → 必须修复后才能继续。**
**WARNING 检查失败 → 应修复，但不阻塞。**

---

## CRITICAL 检查（阻塞）

### C1: 裸 new/delete 检测

```
检查：grep -rn '\bnew\b\s' --include='*.cpp' --include='*.h' src/ | grep -v 'make_unique\|make_shared\|placement new\|operator new'
       grep -rn '\bdelete\b\s' --include='*.cpp' --include='*.h' src/

错误：{file}:{line} — 检测到裸 new/delete。
修复：将 `new T(args)` 替换为 `std::make_unique<T>(args)`。
      将 `delete ptr` 替换为让 unique_ptr 自动析构（移除 delete 语句，确保所有权由 unique_ptr 管理）。
      参考：HARNESS.md §「不变量」→ 内存管理。
```

### C2: 平台代码泄漏

```
检查：grep -rn '#ifdef\s*_WIN32\|#ifdef\s*__APPLE__\|#ifdef\s*__ANDROID__' --include='*.cpp' --include='*.h' src/core/ src/app/ app/

错误：{file}:{line} — 平台宏出现在 src/core/ 或 app/ 中。
修复：将平台特定代码移动到 src/platform/<平台>/ 目录。
      在 src/core/ 中通过抽象接口（见 src/platform/platform.h）访问平台能力。
      参考：IO_MAP.md §「平台条件编译宏映射」→ 禁止用法。
```

### C3: 密钥/凭证硬编码

```
检查：grep -rn 'password\s*=\s*"\|api_key\s*=\s*"\|token\s*=\s*"\|secret\s*=\s*"' --include='*.cpp' --include='*.h' -i src/

错误：{file}:{line} — 疑似硬编码密钥。
修复：移除硬编码值，改用环境变量或平台密钥链。
      参考：IO_MAP.md §「禁止写入文件的内容」。
```

### C4: 异常跨模块边界

```
检查：在导出函数（标记 MY_API）或 JNI 函数中，检查是否有未捕获的异常路径。

错误：{file}:{line} — 导出函数 {func_name} 可能抛出异常跨越模块边界。
修复：在函数入口添加 try-catch，将异常转换为 Result<T, Error> 返回值。
      参考：REVIEW.md §4「错误处理」。
```

### C5: 公共头文件暴露第三方类型

```
检查：在 include/ 目录下的头文件中，检查是否 #include 了第三方库头文件。

错误：{file}:{line} — 公共头文件包含第三方库 {lib_name}。
修复：使用前向声明或 Pimpl 模式隐藏第三方依赖。
      参考：REVIEW.md §6「ABI 兼容性」。
```

---

## HIGH 检查（应修复）

### H1: 文件大小超限

```
检查：wc -l {file}
      头文件 > 300 行 → HIGH
      实现文件 > 500 行 → HIGH
      任何文件 > 800 行 → CRITICAL

错误：{file} — {lines} 行，超过 {limit} 行限制。
修复：按职责拆分文件。提取类型定义到 <模块>/types.h，
      提取辅助函数到 <模块>/utils.cpp。
      参考：BOOTSTRAP.md §「语言、风格与约定」。
```

### H2: 函数过长

```
检查：分析函数体行数，> 50 行为违规。

错误：{file}:{line} — 函数 {func_name} 有 {lines} 行，超过 50 行限制。
修复：提取子函数。每个子函数应有单一职责和描述性名称。
```

### H3: 嵌套过深

```
检查：分析代码缩进层级，> 4 层为违规。

错误：{file}:{line} — 嵌套深度 {depth} 层，超过 4 层限制。
修复：使用 early return、guard clause 或提取子函数减少嵌套。
```

### H4: include 顺序错误

```
检查：验证 #include 顺序：对应头 → 项目内 → 第三方 → 标准库。

错误：{file}:{line} — include 顺序不正确。
修复：按以下顺序重排：
      1. 对应的头文件（foo.cpp → foo.h）
      2. 项目内头文件
      3. 第三方库头文件
      4. 标准库头文件
      参考：BOOTSTRAP.md §「语言、风格与约定」。
```

### H5: 可变状态暴露

```
检查：在公共头文件中，检查是否有非 const 的公共成员变量。

错误：{file}:{line} — 类 {class_name} 暴露了可变公共成员 {member}。
修复：将成员设为 private，提供 const getter。
      如需修改，提供 with_{member}() 方法返回新对象。
      参考：HARNESS.md §「不变量」→ 不可变性。
```

---

## WARNING 检查（建议修复）

### W1: 命名规范

```
检查：文件名非 snake_case → WARNING
      类名非 PascalCase → WARNING
      函数/变量名非 snake_case → WARNING

错误：{file}:{line} — {name} 不符合命名规范（期望 {expected_case}）。
修复：重命名为 {suggested_name}。
      参考：BOOTSTRAP.md §「语言、风格与约定」→ 命名规范。
```

### W2: TODO 残留

```
检查：grep -rn 'TODO\|FIXME\|HACK\|XXX' --include='*.cpp' --include='*.h' src/

错误：{file}:{line} — 残留 {tag}: {content}。
修复：解决 TODO 中描述的问题，然后移除注释。
      如果是已知限制，改写为正式文档注释说明原因。
```

### W3: 缺少错误处理

```
检查：调用可能失败的函数（文件 I/O、网络、解析）后未检查返回值。

错误：{file}:{line} — 调用 {func_name} 后未检查返回值。
修复：检查 Result/expected 的返回值，处理错误情况。
      参考：REVIEW.md §4「错误处理」。
```

---

## 添加新规则

当 LESSONS_LEARNED.md 中的模式错误被人类确认后，按以下格式添加新规则：

```
### {级别}{编号}: {简短描述}

\```
检查：{如何检测}

错误：{file}:{line} — {错误描述}。
修复：{具体修复步骤}。
      参考：{相关文档路径}。
\```
```

**关键：修复指令必须具体到 agent 可直接执行，不能只说"请修复"。**
