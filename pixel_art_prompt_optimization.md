---

# Q版游戏像素风人物提示词优化指南 (Pixel Art Prompt Optimization)

为了让 AI 绘图模型（如 Midjourney, Stable Diffusion XL, DALL-E 3）精准输出符合游戏开发需求的素材，我们将原有的简单描述进行了“工业级”的结构化升级。

像素画在 AI 生成时最容易遇到三大痛点：
1.  **背景不纯**：说是绿色，但生成了草地或有渐变，导致无法一键抠图。
2.  **人物贴边**：角色的头或脚顶到了画布边缘，导致素材残缺。
3.  **多图拼接 (Grid)**：AI 喜欢自作聪明地生成 2x2 或 3x3 的角色预览图，而不是我们要的单张独立图。

以下优化方案通过引入**强制性负面提示词**、**精确的色彩定义**和**布局约束**，完美解决上述问题。

---

## 🚀 最终优化提示词 (Optimized Prompts)

我们将提示词分为“正向（你想要的）”和“负面（你不想要的）”两部分。**负面提示词在像素画生成中至关重要，请务必使用。**

### 1. 英文专业版 (推荐，适用于 Midjourney/SDXL，精准度最高)

这个版本使用了更专业的游戏美术术语（如 `sprite`, `chroma key`, `asset sheet`），AI 理解得最透彻。

> **✅ Positive Prompt (复制到输入框):**
> **A full-body chibi character resembling Shin-chan, 8-bit retro video game pixel art style. Exaggerated cute facial features, giant head and tiny body ratio. Clean sharp black outlines, solid flat color blocks, precise pixel grid details, no anti-aliasing. The character is perfectly centered with ample blank margin space around all sides (top, bottom, left, right). Solid pure green screen background, chroma key green, hex code #00FF00. Single isolated sprite, game asset format. --ar 12:13 --v 6.0**

> **❌ Negative Prompt (复制到负面提示词框):**
> **grid, collage, split screen, multiple frames, character sheet, reference sheet, cropped, cut off, partially visible, blurred, anti-aliasing, smooth edges, photographic, 3d render, gradient background, textured background, shadows on background.**

---

### 2. 中文直译版 (适用于国内支持中文的模型，如 MJ 中文版或某些 SD 模型)

如果使用的模型对英文术语理解不佳，可以使用此中文版，强调了核心约束条件。

> **✅ 正向提示词:**
> **蜡笔小新Q版全身角色，8位复古电子游戏像素艺术风格。表情生动夸张，大头小身躯比例，呆萌可爱。清晰锐利的黑色轮廓线，干净的纯色块，精确的像素点细节，无抗锯齿。角色必须绝对居中，上下左右四周留出充足的空白边缘（不要贴边）。纯正实心绿幕背景，抠像专用绿，十六进制色号#00FF00。单人，独立的精灵图(sprite)，游戏素材格式。**

> **❌ 反向提示词 (负面提示词):**
> **拼图，四宫格，多图拼接，角色设定图，多角度视图，边缘裁剪，身体被切断，模糊，抗锯齿，平滑边缘，3D渲染，照片真实感，渐变背景，有纹理的背景。**

---

## 🛠️ 优化核心解析 (为什么这么改？)

我们将原需求拆解为五个关键维度进行精准控制：

#### 1. 彻底消灭“多格拼图” (Anti-Grid Strategy)
*   **痛点**：AI 听到“像素人物设计”，往往会生成一张包含正视图、侧视图的 2x2 拼图。
*   **解决方案**：
    *   正向加入了 `Single isolated sprite` (单张独立精灵) 和 `game asset format` (游戏素材格式)。
    *   负向死磕了 `grid, collage, split screen, multiple frames, character sheet`，强制模型只能“画一个”。

#### 2. 确保“工业级绿幕” (Pure Green Screen)
*   **痛点**：只写“绿色背景”，AI 可能会生成草地、有光影变化的绿墙，后期抠图极为痛苦。
*   **解决方案**：
    *   使用了三重保险的描述：`Solid pure green screen background` (纯色实心绿幕) + `chroma key green` (抠像专用绿) + `#00FF00` (直接指定最纯的 RGB 绿色号)。确保背景是死板的、毫无杂质的纯绿。

#### 3. 解决“人物贴边残缺” (完美构图)
*   **痛点**：生成的角色经常头顶着上边框，脚踩着下边框，导致素材不可用。
*   **解决方案**：
    *   加入了强制布局指令：`perfectly centered with ample blank margin space around all sides` (绝对居中，且四周留出充足的空白余地)。这能让角色像展示品一样悬浮在画面中央。

#### 4. 强化“像素感” (Pixel Perfect)
*   **痛点**：现在的 AI 模型太先进，生成的像素画有时候为了“好看”会自动添加模糊和抗锯齿，失去了复古感。
*   **解决方案**：
    *   正向强调：`precise pixel grid details` (精准的像素网格细节) 和 `clean sharp black outlines` (干净锐利的黑边)。
    *   负向禁止：`blurred, anti-aliasing, smooth edges` (模糊、抗锯齿、平滑边缘)。

#### 5. 尺寸与比例校准 (Aspect Ratio)
*   **需求**：目标尺寸 192×208。
*   **解决方案**：192 ÷ 208 ≈ 0.923。最接近的整数比是 12:13。在 Midjourney 中使用 `--ar 12:13` 可以确保画布比例正确，像素点横平竖直不变形。（如果在 Stable Diffusion 中，直接设置分辨率为 192x208 或其倍数即可）。