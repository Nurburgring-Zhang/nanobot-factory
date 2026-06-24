---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3045022100db5abbd7388a6943abb9b62d6b25cc47f367595c3aa6eb5bb20f2fccc8cb492a02203bcd42151aa9a0033e2cedcffcd89e387d4cb86db4d7902e880629337806500c
    ReservedCode2: 3045022100945354e7f01270dfa6aafabe198467f0f9146ef471cbe12b293f27504c9943a80220428bb36374738fd25a277214faddbfe60ebdc6c0bdda49a0e7f68c338776be33
---

# Content Structure Plan - General AIGC Enhanced Web App

## 1. Material Inventory

**Core Assets:**
- `imgs/icons/`: SVG icons for 4 main modules + 7 sub-modules (need generation/sourcing)
- `models/`: Placeholder lists for checkpoints (SDXL, SD1.5, Flux)
- `presets/`: Style templates (Anime, Realistic, Oil Painting, Cyberpunk)

**Data Structure (Mock):**
- `data/models.json`: List of available models with metadata (type, size, thumbnail)
- `data/loras.json`: Available LoRA networks
- `data/styles.json`: Style presets with prompt templates

## 2. Website Structure

**Type:** Heavy SPA (Single Page Application)
**Reasoning:**
- **High Interactivity:** AIGC tools require real-time state management (generation progress, canvas manipulation).
- **Persistent Context:** User settings (model selection, prompts) must persist while switching views.
- **Desktop-Like Experience:** The "Krita AI" feel demands a seamless, app-like interface without page reloads.

## 3. Page/Section Breakdown

### Global Layout
- **Sidebar (Left):** Main Navigation (4 Core Modules) + Project Management
- **Workspace (Center):** Canvas / Preview / Node Graph
- **Control Panel (Right):** The 7 Sub-modules (Collapsible Accordion)

### Module 1: Image Generation (`/image-gen`)
**Purpose:** Text-to-Image & Image-to-Image workflows.

| Section | Component Pattern | Data Source | Content Description | Visual Asset |
| :--- | :--- | :--- | :--- | :--- |
| **Model** | Model Selector Card | `data/models.json` | Checkpoint selection, VAE, Clip Skip | Model Thumbnails |
| **Prompt** | Prompt Input Area | User Input | Positive/Negative prompt, Style presets | - |
| **LoRA** | List Item + Slider | `data/loras.json` | LoRA selection & weight control | LoRA Covers |
| **ControlNet** | Upload + Param Block | User Upload | Reference image, preprocessor settings | Reference Preview |
| **Params** | Form Grid | - | Steps, CFG, Seed, Sampler | - |
| **Resolution** | Aspect Ratio Grid | - | Width/Height sliders, common ratios | Aspect Icons |
| **Optimization** | Toggle List | - | Hires. fix, Refiner settings | - |

### Module 2: Image Editor (`/image-edit`)
**Purpose:** Inpainting, Outpainting, AI Upscaling.

| Section | Component Pattern | Data Source | Content Description | Visual Asset |
| :--- | :--- | :--- | :--- | :--- |
| **Canvas** | Interactive Canvas | User Upload | Brush tool, Masking, Layer management | Cursor/Brush Icons |
| **Tools** | Toolbar (Vertical) | - | Brush size, softness, eraser, undo/redo | Tool Icons |
| **Inpaint Params** | Form Block | - | Mask blur, Inpaint area (Whole/Masked) | - |
| **(Reuse)** | 7 Sub-modules | - | Same model/prompt/param controls as Gen | - |

### Module 3: Video Generation (`/video-gen`)
**Purpose:** Text-to-Video, Image-to-Video.

| Section | Component Pattern | Data Source | Content Description | Visual Asset |
| :--- | :--- | :--- | :--- | :--- |
| **Motion** | Slider Group | - | Motion bucket id, FPS, Duration | - |
| **Camera** | Camera Control | - | Pan, Tilt, Zoom, Roll controls | Camera Icons |
| **Input** | Dropzone | User Upload | Initial image (for I2V) | - |
| **(Reuse)** | 7 Sub-modules | - | Adapted for video (e.g., Video Models) | - |

### Module 4: 3D Generation (`/3d-gen`)
**Purpose:** Text-to-3D, Image-to-3D.

| Section | Component Pattern | Data Source | Content Description | Visual Asset |
| :--- | :--- | :--- | :--- | :--- |
| **Preview** | 3D Viewer (Three.js) | Generated Model | Orbit controls, Wireframe/Texture toggle | - |
| **Settings** | Form Block | - | Mesh resolution, Texture quality, Format (OBJ/GLB) | - |
| **(Reuse)** | 7 Sub-modules | - | Adapted for 3D (e.g., Point-E/Shap-E models) | - |

## 4. Content Analysis

**Information Density:** High
**Reasoning:** Professional tools require dense information (many parameters visible at once) to reduce clicks.
**Content Balance:**
- **Controls (Text/UI):** 40% (High density forms)
- **Canvas (Visual):** 60% (Focus on the artwork)
