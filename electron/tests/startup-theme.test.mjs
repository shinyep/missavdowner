import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'

const currentFile = fileURLToPath(import.meta.url)
const projectRoot = path.resolve(path.dirname(currentFile), '..', '..')
const preloadSource = fs.readFileSync(path.join(projectRoot, 'electron', 'preload.ts'), 'utf8')
const mainSource = fs.readFileSync(path.join(projectRoot, 'electron', 'main.ts'), 'utf8')

assert.match(
  mainSource,
  /backgroundColor:\s*'#fff8f4'/,
  '启动窗口底色应与主界面背景色保持一致'
)

assert.match(
  preloadSource,
  /background:\s*linear-gradient\(180deg,\s*#fff8f4 0%,\s*#fbebdd 100%\);/,
  '启动遮罩应使用浅暖色渐变背景'
)

assert.match(
  preloadSource,
  /background:\s*#ff9800;/,
  '启动动画主色应使用主题橙色'
)

console.log('startup-theme assertions passed')
