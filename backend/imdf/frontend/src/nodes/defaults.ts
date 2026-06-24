/**
 * IMDF 节点默认数据工厂 (R3-Worker-4)
 * --------------------------------------------------------------------
 * 每个节点类型的默认 data 形状,集中维护,避免在节点组件里硬编码
 * `||` 兜底默认值。
 *
 * 使用:
 *   const data = getDefaultData('image')  // → ImageNodeData 的默认形态
 *   const data = { ...getDefaultData('text'), prompt: 'hello' }  // 合并用户配置
 * --------------------------------------------------------------------
 */

import type { NodeDataMap, NodeTypeKey } from './types';

/** 给定节点类型,返回其默认 data 形状 */
export function getDefaultData<T extends NodeTypeKey>(type: T): NodeDataMap[T] {
  return DEFAULTS[type] as NodeDataMap[T];
}

/** 给定节点类型,返回默认 data 形状 (unknown 版本) */
export function getDefaultDataUnknown(type: string): Record<string, unknown> {
  return (DEFAULTS as unknown as Record<string, Record<string, unknown>>)[type] ?? {};
}

/** 合并 user 提供的 data 和默认 data,user 字段优先 */
export function mergeDefaultData<T extends NodeTypeKey>(
  type: T,
  user: Partial<NodeDataMap[T]> | undefined,
): NodeDataMap[T] {
  const base = DEFAULTS[type] as unknown as Record<string, unknown>;
  return { ...base, ...(user ?? {}) } as NodeDataMap[T];
}

// ─── 默认值集中表 ────────────────────────────────────────────────────────────

const DEFAULTS: { [K in NodeTypeKey]: NodeDataMap[K] } = {
  'idea': {
    title: '',
    content: '',
    status: 'idle',
  },
  'bp': {
    title: '项目蓝图',
    steps: [],
    status: 'idle',
  },
  'text': {
    prompt: '',
    text: '',
    rhNodeId: '',
    status: 'idle',
  },
  'combine': {
    direction: 'horizontal',
    status: 'idle',
  },
  'resize': {
    width: 1024,
    height: 1024,
    fit: 'cover',
    status: 'idle',
  },
  'upscale': {
    scale: 2,
    status: 'idle',
  },
  'remove-bg': {
    status: 'idle',
  },
  'frame-extractor': {
    interval: 1,
    count: 8,
    status: 'idle',
  },
  'frame-pair': {
    status: 'idle',
  },
  'grid-crop': {
    rows: 2,
    cols: 2,
    status: 'idle',
  },
  'grid-editor': {
    rows: 2,
    cols: 2,
    cells: [],
    status: 'idle',
  },
  'image': {
    model: 'gpt-image-2',
    ratio: '1:1',
    size: '1024x1024',
    n: 1,
    referenceImages: [],
    status: 'idle',
  },
  'image-compare': {
    leftUrl: '',
    rightUrl: '',
    status: 'idle',
  },
  'video': {
    kind: 'veo',
    model: '',
    ratio: '16:9',
    duration: 5,
    fps: 24,
    referenceImages: [],
    status: 'idle',
  },
  'video-output': {
    status: 'idle',
  },
  'audio': {
    model: 'tts-1',
    voice: 'alloy',
    text: '',
    speed: 1.0,
    pitch: 1.0,
    status: 'idle',
  },
  'llm': {
    model: 'gpt-4o-mini',
    systemPrompt: '',
    prompt: '',
    temperature: 0.7,
    maxTokens: 2048,
    status: 'idle',
  },
  'loop': {
    mode: 'for',
    count: 1,
    items: [],
    status: 'idle',
  },
  'relay': {
    status: 'idle',
  },
  'output': {
    status: 'idle',
  },
  'browser': {
    url: '',
    method: 'GET',
    headers: {},
    body: '',
    status: 'idle',
  },
  'idea_shortcut': {
    label: '',
    status: 'idle',
  },
  'placeholder': {
    label: '',
  },
  'aggregate-parser': {
    url: '',
    platform: '',
    status: 'idle',
  },
  'comfy-ui-app-maker': {
    appId: '',
    appName: '',
    inputs: {},
    status: 'idle',
  },
  'comfy-ui-store': {
    query: '',
    category: '',
    apps: [],
    status: 'idle',
  },
  'running-hub': {
    appId: '',
    apiKey: '',
    inputs: {},
    status: 'idle',
  },
  'rh-config': {
    apiKey: '',
    baseUrl: 'https://www.runninghub.cn',
    maxConcurrent: 3,
    status: 'idle',
  },
  'rh-tools': {
    selectedAppId: '',
    inputs: {},
    status: 'idle',
  },
  'rh-toolbox': {
    toolId: '',
    inputs: {},
    status: 'idle',
  },
  'fal-toolbox': {
    modelId: '',
    inputs: {},
    status: 'idle',
  },
  'toolbox-param': {
    params: [],
    status: 'idle',
  },
  'grok-oauth-agent': {
    model: 'grok-2',
    systemPrompt: '',
    prompt: '',
    oauthToken: '',
    status: 'idle',
  },
  'group-box': {
    label: '分组',
    color: '#94a3b8',
    width: 320,
    height: 240,
  },
  'drawing-board': {
    strokes: [],
    status: 'idle',
  },
  'material-set': {
    kind: 'character',
    items: [],
    selectedItemIds: [],
    status: 'idle',
  },
  'material-preview-section': {
    items: [],
  },
  'material-thumbnail': {
    itemId: '',
    label: '',
    active: false,
  },
  'pick-from-set': {
    setId: '',
    selectedItemId: '',
    status: 'idle',
  },
  'portrait-metadata': {
    name: '',
    age: '',
    gender: '',
    appearance: '',
    outfit: '',
    personality: '',
    background: '',
    status: 'idle',
  },
  'portrait-master': {
    presetId: 'default',
    viewId: 'front',
    shotId: 'half',
    intensityId: 'natural',
    language: 'zh',
    customText: '',
    status: 'idle',
  },
  'pose-master': {
    presetId: 'standing',
    viewId: 'front',
    shotId: 'full-body',
    intensityId: 'natural',
    language: 'zh',
    poseHasPeople: true,
    posePeople: [],
    poseActivePersonIndex: 0,
    posePointVersion: 4,
    poseCanvasRatioId: 'default',
    poseCanvasCustomWidth: 620,
    poseCanvasCustomHeight: 520,
    status: 'idle',
  },
  'preset-image': {
    presetId: '',
    status: 'idle',
  },
  'remove-ai-watermark': {
    sourceUrl: '',
    status: 'idle',
  },
  'seedance': {
    mode: 'omni',
    duration: 5,
    ratio: '16:9',
    referenceImages: [],
    status: 'idle',
  },
  'storyboard-grid': {
    shots: [],
    rows: 2,
    cols: 3,
    status: 'idle',
  },
  'text-split': {
    text: '',
    separator: '\n',
    chunks: [],
    maxChunkSize: 2000,
    status: 'idle',
  },
  'topaz-image-upscale': {
    scale: 2,
    status: 'idle',
  },
  'topaz-video-upscale': {
    scale: 2,
    status: 'idle',
  },
  'upload': {
    files: [],
    status: 'idle',
  },
  'audio-upload': {
    files: [],
    status: 'idle',
  },
};
