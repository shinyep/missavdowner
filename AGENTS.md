# 项目规则

## 版本号管理（强制）

**每次更新代码、修复 bug、重新编译和打包之前，必须先更新 `package.json` 中的 `version` 字段。**

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范（`MAJOR.MINOR.PATCH`）：

- **PATCH**（补丁）：修复 bug、小改动，不影响功能接口 → `1.1.4` → `1.1.5`
- **MINOR**（次版本）：新增功能，向后兼容 → `1.1.5` → `1.2.0`
- **MAJOR**（主版本）：破坏性变更，不向后兼容 → `1.2.0` → `2.0.0`

### 执行流程

1. 修改代码前，先更新 `package.json` 中的 `version`
2. 提交代码时，commit message 中注明新版本号
3. 然后再执行编译和打包操作

### 示例

```json
// 修改前
"version": "1.1.4"

// 修复 bug 后
"version": "1.1.5"
```


## 中文编码规范（强制）

**所有涉及中文内容的文件，必须使用 UTF-8 编码，避免乱码问题。**

### 适用范围

- 源代码文件（`.ts`、`.vue`、`.js`、`.css` 等）
- 配置文件（`.json`、`.yaml`、`.toml` 等）
- 文档文件（`.md`、`.txt` 等）
- Python 脚本（`.py`）
- HTML 模板文件

### 具体要求

- PowerShell 写入/读取中文文件时，必须指定 `-Encoding utf8`
- Python 文件顶部添加编码声明：`# -*- coding: utf-8 -*-`
- HTML 文件 `<head>` 中包含：`<meta charset="UTF-8">`
- Git 提交信息中的中文使用 UTF-8 编码
- 数据库连接和文件 I/O 操作统一使用 UTF-8
