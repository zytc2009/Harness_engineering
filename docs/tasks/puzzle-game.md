# Task

## Goal

实现一个网页版拼图小游戏：支持用户上传图片，将其切割为可配置数量的拼图块，玩家用鼠标拖拽还原图片，完成后记录用时并写入本地排行榜。

## Scope

- In scope:
  - 图片上传（浏览器文件选择，支持 PNG/JPG）
  - 拼图块切割（行列数可配置，默认 4×4）
  - 鼠标拖拽交互（拾起、移动、放下、对齐吸附）
  - 计时器（从第一次移动开始计时，完成时停止）
  - 排行榜（localStorage 持久化，记录 Top 10，显示姓名+用时）
  - 胜利检测与胜利界面
- Out of scope:
  - 网络联机 / 在线排行榜
  - 音效 / 背景音乐
  - 撤销/重做
  - 移动端适配

## Inputs

- 用户通过浏览器文件上传控件选择本地图片
- 切割行列数通过页面 UI 控件配置（默认 4×4）
- 排行榜数据存储于浏览器 `localStorage`

## Outputs

- 单文件或多文件网页：`index.html`、`puzzle.js`、`style.css`
- 无需构建工具，直接浏览器打开即可运行
- Jest 单元测试覆盖核心逻辑（切割算法、对齐判断、排行榜读写）

## Acceptance Criteria

- 上传图片后显示随机打散的拼图块，鼠标可拖拽每块
- 拼图块放置到正确位置时自动吸附锁定
- 全部还原后弹出"完成"界面，显示用时和排名
- 排行榜按用时升序排列，刷新页面后仍可读取（localStorage）
- 行列数控件改变切割粒度后游戏正常运行
- 单元测试全部通过（Jest）

## Constraints

- language: javascript
- platform: browser
- rendering: HTML5 Canvas
- framework: 原生 JS，不使用第三方框架（无 React/Vue）
- test_framework: Jest（Node.js 环境，通过 npm 安装）
- persistence: localStorage
- dependency_policy: 运行时零依赖，测试依赖仅 Jest
- forbidden_paths: harness-cpp/、harness-runtime/、docs/、skills/

## Status

ready
