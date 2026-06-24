---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3046022100e0c429422319387af9d73c7bdcc843be886942329e956d6df90965f89281a632022100a0b7e2f6d9ce96a62c80375643c716d7da42283f32ee8f82502d3ae15f1b65d0
    ReservedCode2: 3045022100af7a81fa784334b514ef82ab5a2de9c49f80c2f08e7196b8fd30c2f9e0c378a8022018757753d565c8adf56dc9a9059dbe6331ec38f79ebebe0550ba28baaf9e5371
---

# Design Specification - General AIGC Enhanced Web App

## 1. Direction & Rationale

**Design Essence:**
"Professional Immersion." The interface mimics high-end desktop creative software (Krita 7.0, Blender, Unreal Engine) rather than a typical website. It prioritizes **focus** (dark environment), **density** (lots of controls in small space), and **precision** (sliders, inputs).

**Visual Language:**
Deep Indigo (#1e1b4b) backgrounds create a calm, creative atmosphere, distinct from the harsh "pure black" of developer tools. Cyan (#06b6d4) accents provide a futuristic "AI" feel without being distracting.

**References:**
- **Krita 5.2/7.0**: Dockable panels, dense toolbars.
- **ComfyUI**: Node-graph complexity but tamed.
- **Adobe Lightroom**: Slider density and histogram visualization.

---

## 2. Design Tokens

### 2.1 Colors (Deep Indigo Theme)

| Role | Token Name | Value | Description |
| :--- | :--- | :--- | :--- |
| **Primary** | `primary-900` | `#1e1b4b` | Main App Background (Deepest Indigo) |
| | `primary-800` | `#312e81` | Panel Backgrounds / Sidebar |
| | `primary-700` | `#4338ca` | Input Backgrounds / Inactive States |
| **Accent** | `accent-500` | `#06b6d4` | Primary Action / Active State (Cyan) |
| | `accent-400` | `#22d3ee` | Hover State |
| **Neutral** | `neutral-900` | `#0f172a` | Canvas Background (Slate) |
| | `text-100` | `#f1f5f9` | Primary Text (High Contrast) |
| | `text-400` | `#94a3b8` | Labels / Secondary Text |
| **Semantic** | `success` | `#10b981` | Generation Complete |
| | `error` | `#ef4444` | Out of Memory / Net Error |

### 2.2 Typography (System UI)

**Font Family:** `Inter`, system-ui, sans-serif (Clean, legible at small sizes).

| Role | Size | Weight | Line Height | Usage |
| :--- | :--- | :--- | :--- | :--- |
| **H1** | 24px | 600 | 1.2 | Module Titles |
| **H2** | 18px | 600 | 1.3 | Panel Headers |
| **Body** | 13px | 400 | 1.4 | Standard Labels |
| **Small** | 12px | 400 | 1.2 | Help Text / Values |
| **Tiny** | 10px | 500 | 1.0 | Badges / Tags |

### 2.3 Spacing & Shape (Dense)

- **Grid Base:** 4px
- **Spacing Scale:**
    - `xs`: 4px (Icon gap)
    - `sm`: 8px (Element gap)
    - `md`: 12px (Section gap)
    - `lg`: 16px (Panel padding)
- **Border Radius:**
    - `sm`: 4px (Inputs, Buttons - Sharp/Professional)
    - `md`: 6px (Cards, Panels)
    - `full`: 999px (Pills, Toggles)

---

## 3. Component Specifications (Key Modules)

### 3.1 Primary Navigation (Left Sidebar)
**Structure:**
- Fixed width: 64px (Icon only) -> Expand on hover (200px)
- Background: `primary-800`
- Border-right: 1px solid `primary-700`

**Item State:**
- **Idle:** Icon (text-400)
- **Hover:** Bg `primary-700`, Icon `text-100`
- **Active:** Bg `accent-500` (10% opacity), Icon `accent-400`, Left-border 3px `accent-500`

### 3.2 Parameter Accordion (Right Sidebar)
**Structure:**
- Width: 320px - 400px (Resizable)
- Background: `primary-800`
- Scrollable vertical list of 7 modules.

**Accordion Item:**
- **Header:** Height 40px, Bg `primary-800`, Border-bottom 1px `primary-700`. Chevron icon right.
- **Content:** Padding 12px. Grid layout for controls.

### 3.3 Control Inputs (The "Dense" Look)
**Slider + Number Input Combo:**
- **Layout:** [Label (flex)] [Slider (flex-grow)] [Input (50px)]
- **Slider:** Track `primary-900` (4px), Fill `accent-500`, Thumb 12px circle (white).
- **Input:** Bg `primary-900`, Text `text-100`, No border, Right-aligned.

**Select Dropdown:**
- Height: 32px (Compact)
- Bg: `primary-700`
- Border: 1px solid `primary-600`
- Text: 13px

### 3.4 The Canvas (Center)
**Structure:**
- Bg: `neutral-900` (Checkered pattern option)
- **Toolbar (Floating):** Top-center or Bottom-center. Glassmorphism `primary-800` (80% opacity).
- **Zoom/Pan:** Infinite canvas behavior.

### 3.5 Generation Queue / Progress
**Location:** Top bar or overlay.
**Visual:**
- Thin progress bar (2px) at very top `accent-500`.
- Status Text: "Generating... (2.4s/it)" in Navbar right.

---

## 4. Layout & Responsive Patterns

### 4.1 Desktop (Default) - "The Cockpit"
`[ Nav (64px) ] [ Canvas (Flex) ] [ Parameters (340px) ]`
- **Nav:** Fixed left.
- **Params:** Fixed right, scrollable.
- **Canvas:** Fills remaining space.

### 4.2 Tablet (768px - 1024px)
`[ Nav (64px) ] [ Canvas (Flex) ]`
- **Params:** Moves to a **Drawer** (Slide-over) triggered by a "Settings" FAB (Floating Action Button) on the right.

### 4.3 Mobile (< 768px)
`[ Canvas (Flex) ]`
- **Nav:** Bottom Tab Bar.
- **Params:** Bottom Sheet (Swipe up to configure).
- **Optimization:** Hide complex sliders, show "Presets" first.

---

## 5. Interaction & Motion

**Principles:** "Instant & Subtle".
- **Hover:** Instant color shift (0ms delay, 150ms transition).
- **Panel Collapse:** 250ms `ease-in-out`.
- **Generation:**
    - Start: Button shows spinner.
    - Progress: Real-time preview (LCM/Turbo) updates canvas every step.
    - Complete: Subtle flash overlay on canvas + Success toast.

**Micro-interactions:**
- **Sliders:** Thumb expands slightly on active/drag.
- **Toggles:** Smooth color fill transition.
- **Inputs:** Focus ring `accent-500` (1px) glow.
