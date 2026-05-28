---
name: skill-echo-test
description: 一个最小测试 skill，用于验证 agent 是否能成功发现、调用并返回 skill 结果。
---

# Skill Echo Test

## 目的
- 用来测试 skill 接入链路是否正常。

## 行为要求
- 收到任务后，直接返回一个简短、稳定、可识别的结果。
- 不要扩展推理，不要编造额外内容。

## 输出格式
固定返回以下结构：

TEST_SKILL_OK
- task: <任务摘要>
- input: <输入摘要>