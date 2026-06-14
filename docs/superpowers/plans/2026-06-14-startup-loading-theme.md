# 启动准备界面主题统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Electron 启动准备界面的黑色背景改为与当前浅暖色主题一致的配色，并保留现有启动流程。

**Architecture:** 通过一个文件级回归测试锁定目标主题色，再分别修改窗口创建时的底色与预加载遮罩样式。改动只触及 Electron 启动层，不进入 Vue 业务界面。

**Tech Stack:** Electron、TypeScript、Node.js 文件断言脚本

---

### Task 1: 建立回归测试

**Files:**
- Create: `electron/tests/startup-theme.test.mjs`
- Test: `electron/tests/startup-theme.test.mjs`

- [ ] **Step 1: 写出失败测试**

```js
import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'

const preloadSource = fs.readFileSync(path.resolve('electron/preload.ts'), 'utf8')
const mainSource = fs.readFileSync(path.resolve('electron/main.ts'), 'utf8')

assert.match(mainSource, /backgroundColor:\s*'#fff8f4'/)
assert.match(preloadSource, /background:\s*linear-gradient\(180deg,\s*#fff8f4 0%,\s*#fbebdd 100%\)/)
assert.match(preloadSource, /background:\s*#ff9800/)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `node electron/tests/startup-theme.test.mjs`
Expected: FAIL，因为当前代码仍然包含深色背景值

### Task 2: 修改启动主题色

**Files:**
- Modify: `electron/main.ts`
- Modify: `electron/preload.ts`
- Test: `electron/tests/startup-theme.test.mjs`

- [ ] **Step 1: 修改窗口底色**

```ts
backgroundColor: '#fff8f4',
```

- [ ] **Step 2: 修改预加载遮罩与动画颜色**

```ts
background: #ff9800;
```

```ts
background: linear-gradient(180deg, #fff8f4 0%, #fbebdd 100%);
```

- [ ] **Step 3: 重新运行测试确认通过**

Run: `node electron/tests/startup-theme.test.mjs`
Expected: PASS

- [ ] **Step 4: 运行构建验证**

Run: `npm run build`
Expected: exit 0
