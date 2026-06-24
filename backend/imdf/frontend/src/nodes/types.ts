/**
 * IMDF 节点 IO 数据契约 (R3-Worker-4)
 * --------------------------------------------------------------------
 * 每个节点类型对应一个 *Data 接口,定义:
 *   - data in  : React Flow 节点 data 字段的结构(用户可配置)
 *   - output   : 节点自身计算/产出并写回 data 的字段(下游可读)
 *
 * 设计原则:
 *   1. 所有字段都是可选的,允许节点携带部分配置(渐进式配置)
 *   2. 默认值集中在 defaults.ts → getDefaultData(type)
 *   3. 输出字段在节点 useEffect/useMemo 计算后通过 useUpdateNodeData
 *      写回 data,下游节点用 xyflow useNodesData() 读取
 *   4. status/error/promptResolved 三个字段是所有节点通用的运行态
 * --------------------------------------------------------------------
 */

import type { Node } from '@xyflow/react';

// ─── 通用基础字段 ────────────────────────────────────────────────────────────

/** 节点统一运行态 (所有节点可选携带) */
export interface NodeRunStatus {
  status?: 'idle' | 'running' | 'success' | 'error';
  error?: string | null;
  /** 节点最近一次成功运行的时间戳 (毫秒) */
  lastRunAt?: number;
}

/** 节点 prompt 输出 (resolve 之后的纯文本) */
export interface NodePromptOutput {
  /** 原始 prompt 输入 (可含 @素材 引用) */
  prompt?: string;
  /** 解析 @素材 引用后的纯文本 (供下游直接使用) */
  promptResolved?: string;
  /** prompt 中的素材 mention 列表 */
  promptMentions?: MediaMention[];
}

/** 媒体素材 @mention (在 prompt 文本中 @ 引用的素材) */
export interface MediaMention {
  /** mention 符号,如 "img_1" */
  token: string;
  /** mention 指向的素材 ID */
  materialId: string;
  /** mention 指向的素材类型 */
  kind: 'image' | 'video' | 'audio' | 'text';
}

// ─── 节点类型 → Data Shape 映射 ──────────────────────────────────────────────

export interface IdeaNodeData extends NodeRunStatus, NodePromptOutput {
  title?: string;
  content?: string;
}

export interface BpNodeData extends NodeRunStatus, NodePromptOutput {
  title?: string;
  steps?: Array<{ id: string; text: string; done?: boolean }>;
}

export interface TextNodeData extends NodeRunStatus, NodePromptOutput {
  prompt?: string;
  text?: string;
  rhNodeId?: string;
  size?: { w: number; h?: number };
}

export interface CombineNodeData extends NodeRunStatus {
  direction?: 'horizontal' | 'vertical';
  imageUrl?: string;
  imageUrls?: string[];
}

export interface ResizeNodeData extends NodeRunStatus {
  width?: number;
  height?: number;
  fit?: 'cover' | 'contain' | 'inside' | 'fill';
  imageUrl?: string;
}

export interface UpscaleNodeData extends NodeRunStatus {
  scale?: 1.5 | 2 | 3 | 4;
  imageUrl?: string;
}

export interface RemoveBgNodeData extends NodeRunStatus {
  imageUrl?: string;
}

export interface FrameExtractorNodeData extends NodeRunStatus {
  videoUrl?: string;
  frames?: string[];
  interval?: number; // 秒
  count?: number;
  imageUrls?: string[];
}

export interface FramePairNodeData extends NodeRunStatus {
  firstFrame?: string;
  lastFrame?: string;
  imageUrls?: string[];
}

export interface GridCropNodeData extends NodeRunStatus {
  rows?: number;
  cols?: number;
  imageUrl?: string;
  imageUrls?: string[];
}

export interface GridEditorNodeData extends NodeRunStatus {
  rows?: number;
  cols?: number;
  cells?: Array<{
    index: number;
    imageUrl?: string;
    text?: string;
    prompt?: string;
  }>;
  imageUrls?: string[];
}

export interface ImageNodeData extends NodeRunStatus, NodePromptOutput {
  model?: string; // 模型 ID,例如 'gpt-image-2' / 'nbpro' / 'mj'
  ratio?: string;
  size?: string;
  n?: number; // 生成张数
  referenceImages?: string[];
  urls?: string[];
  imageUrl?: string;
  imageUrls?: string[];
  // MJ 专属
  mjVersion?: string;
  mjRatio?: string;
  mjSpeed?: 'relax' | 'fast' | 'turbo';
  mjSref?: string;
  mjOref?: string;
  // 高级 provider
  providerSource?: string;
  providerId?: string;
  providerModel?: string;
  providerParams?: Record<string, unknown>;
}

export interface ImageCompareNodeData extends NodeRunStatus {
  leftUrl?: string;
  rightUrl?: string;
}

export interface VideoNodeData extends NodeRunStatus, NodePromptOutput {
  kind?: 'veo' | 'grok' | 'sora' | 'seedance' | 'kling' | 'wan' | 'minimax';
  model?: string;
  ratio?: string;
  duration?: number;
  resolution?: string;
  mode?: string;
  fps?: number;
  referenceImages?: string[];
  videoUrl?: string;
  imageUrls?: string[];
  // Seedance
  seedanceMode?: 'omni' | 'first' | 'firstlast' | 'multiframe';
}

export interface VideoOutputNodeData extends NodeRunStatus {
  videoUrl?: string;
  prompt?: string;
}

export interface AudioNodeData extends NodeRunStatus, NodePromptOutput {
  model?: string;
  voice?: string;
  text?: string;
  speed?: number;
  pitch?: number;
  audioUrl?: string;
}

export interface LlmNodeData extends NodeRunStatus, NodePromptOutput {
  model?: string; // 'gpt-4o' | 'claude-3.5-sonnet' | ...
  systemPrompt?: string;
  prompt?: string;
  temperature?: number;
  maxTokens?: number;
  reply?: string;
  outputText?: string;
  providerSource?: string;
  providerId?: string;
}

export interface LoopNodeData extends NodeRunStatus {
  mode?: 'for' | 'while' | 'map' | 'reduce';
  count?: number;
  index?: number;
  items?: unknown[];
  /** 内部状态:已完成迭代数 */
  completed?: number;
}

export interface RelayNodeData extends NodeRunStatus {
  prompt?: string;
  imageUrl?: string;
  imageUrls?: string[];
  videoUrl?: string;
  audioUrl?: string;
  modelUrl?: string;
}

export interface OutputNodeData extends NodeRunStatus, NodePromptOutput {
  // 输入侧:从上游收集
  prompt?: string;
  imageUrl?: string;
  imageUrls?: string[];
  videoUrl?: string;
  audioUrl?: string;
  modelUrl?: string;
  // 用户编辑后的覆盖文本(空 = 回到上游原文)
  outputText?: string;
}

export interface BrowserNodeData extends NodeRunStatus, NodePromptOutput {
  url?: string;
  method?: 'GET' | 'POST';
  headers?: Record<string, string>;
  body?: string;
  response?: string;
}

export interface IdeaNodeDataShape extends NodeRunStatus, NodePromptOutput {
  label?: string;
}

export interface PlaceholderNodeData {
  label?: string;
}

export interface AggregateParserNodeData extends NodeRunStatus {
  url?: string;
  platform?: string;
  parsed?: {
    title?: string;
    cover?: string;
    videoUrl?: string;
    author?: string;
    duration?: number;
  };
  imageUrl?: string;
  videoUrl?: string;
}

export interface ComfyUiAppMakerNodeData extends NodeRunStatus, NodePromptOutput {
  appId?: string;
  appName?: string;
  inputs?: Record<string, unknown>;
  outputImageUrl?: string;
  imageUrl?: string;
}

export interface ComfyUiStoreNodeData extends NodeRunStatus, NodePromptOutput {
  query?: string;
  category?: string;
  apps?: Array<{
    id: string;
    name: string;
    description?: string;
    iconUrl?: string;
  }>;
  selectedAppId?: string;
}

export interface RunningHubNodeData extends NodeRunStatus, NodePromptOutput {
  appId?: string;
  apiKey?: string;
  inputs?: Record<string, unknown>;
  taskId?: string;
  outputImageUrl?: string;
  imageUrl?: string;
  imageUrls?: string[];
}

export interface RhConfigNodeData extends NodeRunStatus {
  apiKey?: string;
  baseUrl?: string;
  maxConcurrent?: number;
}

export interface RhToolsNodeData extends NodeRunStatus {
  selectedAppId?: string;
  inputs?: Record<string, unknown>;
  outputImageUrl?: string;
  imageUrl?: string;
}

export interface RhToolboxNodeData extends NodeRunStatus {
  toolId?: string;
  inputs?: Record<string, unknown>;
  outputImageUrl?: string;
}

export interface FalToolboxNodeData extends NodeRunStatus {
  modelId?: string;
  inputs?: Record<string, unknown>;
  outputImageUrl?: string;
  imageUrl?: string;
}

export interface ToolboxParamNodeData extends NodeRunStatus {
  params?: Array<{
    key: string;
    label: string;
    type: 'string' | 'int' | 'float' | 'bool' | 'select';
    value: unknown;
    options?: string[];
  }>;
}

export interface GrokOAuthAgentNodeData extends NodeRunStatus, NodePromptOutput {
  model?: string;
  systemPrompt?: string;
  prompt?: string;
  reply?: string;
  outputText?: string;
  oauthToken?: string;
}

export interface GroupBoxNodeData {
  label?: string;
  color?: string;
  width?: number;
  height?: number;
}

export interface DrawingBoardNodeData extends NodeRunStatus {
  imageUrl?: string;
  strokes?: Array<{
    id: string;
    points: Array<{ x: number; y: number }>;
    color: string;
    width: number;
  }>;
}

export interface MaterialSetNodeData extends NodeRunStatus {
  kind?: 'character' | 'scene' | 'prop' | 'style' | 'audio';
  items?: Array<{
    id: string;
    name: string;
    imageUrl?: string;
    description?: string;
  }>;
  selectedItemIds?: string[];
}

export interface MaterialPreviewSectionData {
  items?: Array<{
    id: string;
    name: string;
    imageUrl?: string;
    kind: 'image' | 'video' | 'audio' | 'text';
  }>;
  activeId?: string;
}

export interface MaterialThumbnailData {
  itemId: string;
  imageUrl?: string;
  label?: string;
  active?: boolean;
}

export interface PickFromSetNodeData extends NodeRunStatus {
  setId?: string;
  selectedItemId?: string;
  selectedItem?: { id: string; name: string; imageUrl?: string };
}

export interface PortraitMetadataNodeData extends NodeRunStatus, NodePromptOutput {
  name?: string;
  age?: string;
  gender?: string;
  appearance?: string;
  outfit?: string;
  personality?: string;
  background?: string;
}

export interface PortraitMasterNodeData extends NodeRunStatus, NodePromptOutput {
  presetId?: string;
  viewId?: string;
  shotId?: string;
  intensityId?: string;
  language?: 'zh' | 'en';
  customText?: string;
  prompt?: string;
  imageUrl?: string;
}

export interface PoseMasterNodeData extends NodeRunStatus, NodePromptOutput {
  presetId?: string;
  viewId?: string;
  shotId?: string;
  intensityId?: string;
  language?: 'zh' | 'en';
  posePoints?: Array<{ x: number; y: number; name?: string }>;
  posePointVersion?: number;
  poseHasPeople?: boolean;
  posePeople?: Array<Array<{ x: number; y: number; name?: string }>>;
  poseActivePersonIndex?: number;
  poseHandControls?: Record<string, unknown>;
  poseCanvasRatioId?: string;
  poseCanvasCustomWidth?: number;
  poseCanvasCustomHeight?: number;
  prompt?: string;
  imageUrl?: string;
}

export interface PresetImageNodeData extends NodeRunStatus {
  presetId?: string;
  imageUrl?: string;
}

export interface RemoveAiWatermarkNodeData extends NodeRunStatus {
  imageUrl?: string;
  imageUrls?: string[];
  // 17 平台无水印视频解析
  sourceUrl?: string;
  videoUrl?: string;
  parsed?: {
    platform?: string;
    title?: string;
    cover?: string;
  };
}

export interface SeedanceNodeData extends NodeRunStatus, NodePromptOutput {
  mode?: 'omni' | 'first' | 'firstlast' | 'multiframe';
  referenceImages?: string[];
  duration?: number;
  ratio?: string;
  videoUrl?: string;
  imageUrls?: string[];
}

export interface StoryboardGridNodeData extends NodeRunStatus {
  shots?: Array<{
    id: string;
    prompt: string;
    imageUrl?: string;
  }>;
  rows?: number;
  cols?: number;
  imageUrls?: string[];
}

export interface TextSplitNodeData extends NodeRunStatus, NodePromptOutput {
  text?: string;
  separator?: string; // 默认 '\n'
  chunks?: string[];
  maxChunkSize?: number;
}

export interface TopazImageUpscaleNodeData extends NodeRunStatus {
  scale?: 2 | 4 | 6;
  imageUrl?: string;
}

export interface TopazVideoUpscaleNodeData extends NodeRunStatus {
  scale?: 2 | 4;
  videoUrl?: string;
}

export interface UploadNodeData extends NodeRunStatus {
  files?: Array<{
    id: string;
    name: string;
    url: string;
    kind: 'image' | 'video' | 'audio';
  }>;
  imageUrl?: string;
  imageUrls?: string[];
  videoUrl?: string;
  audioUrl?: string;
}

export interface AudioUploadNodeData extends UploadNodeData {}

// ─── 总映射 (string literal 索引) ────────────────────────────────────────────

export interface NodeDataMap {
  idea: IdeaNodeData;
  bp: BpNodeData;
  text: TextNodeData;
  combine: CombineNodeData;
  resize: ResizeNodeData;
  upscale: UpscaleNodeData;
  'remove-bg': RemoveBgNodeData;
  'frame-extractor': FrameExtractorNodeData;
  'frame-pair': FramePairNodeData;
  'grid-crop': GridCropNodeData;
  'grid-editor': GridEditorNodeData;
  image: ImageNodeData;
  'image-compare': ImageCompareNodeData;
  video: VideoNodeData;
  'video-output': VideoOutputNodeData;
  audio: AudioNodeData;
  llm: LlmNodeData;
  loop: LoopNodeData;
  relay: RelayNodeData;
  output: OutputNodeData;
  browser: BrowserNodeData;
  idea_shortcut: IdeaNodeDataShape;
  placeholder: PlaceholderNodeData;
  'aggregate-parser': AggregateParserNodeData;
  'comfy-ui-app-maker': ComfyUiAppMakerNodeData;
  'comfy-ui-store': ComfyUiStoreNodeData;
  'running-hub': RunningHubNodeData;
  'rh-config': RhConfigNodeData;
  'rh-tools': RhToolsNodeData;
  'rh-toolbox': RhToolboxNodeData;
  'fal-toolbox': FalToolboxNodeData;
  'toolbox-param': ToolboxParamNodeData;
  'grok-oauth-agent': GrokOAuthAgentNodeData;
  'group-box': GroupBoxNodeData;
  'drawing-board': DrawingBoardNodeData;
  'material-set': MaterialSetNodeData;
  'material-preview-section': MaterialPreviewSectionData;
  'material-thumbnail': MaterialThumbnailData;
  'pick-from-set': PickFromSetNodeData;
  'portrait-metadata': PortraitMetadataNodeData;
  'portrait-master': PortraitMasterNodeData;
  'pose-master': PoseMasterNodeData;
  'preset-image': PresetImageNodeData;
  'remove-ai-watermark': RemoveAiWatermarkNodeData;
  seedance: SeedanceNodeData;
  'storyboard-grid': StoryboardGridNodeData;
  'text-split': TextSplitNodeData;
  'topaz-image-upscale': TopazImageUpscaleNodeData;
  'topaz-video-upscale': TopazVideoUpscaleNodeData;
  upload: UploadNodeData;
  'audio-upload': AudioUploadNodeData;
}

/** 51 个节点类型 key (覆盖 NodeDataMap 全部 51 项) */
export const ALL_NODE_TYPES = [
  'idea', 'bp', 'text', 'combine', 'resize', 'upscale', 'remove-bg',
  'frame-extractor', 'frame-pair', 'grid-crop', 'grid-editor', 'image',
  'image-compare', 'video', 'video-output', 'audio', 'llm', 'loop',
  'relay', 'output', 'browser', 'placeholder', 'aggregate-parser',
  'comfy-ui-app-maker', 'comfy-ui-store', 'running-hub', 'rh-config',
  'rh-tools', 'rh-toolbox', 'fal-toolbox', 'toolbox-param',
  'grok-oauth-agent', 'group-box', 'drawing-board', 'material-set',
  'pick-from-set', 'portrait-metadata', 'portrait-master', 'pose-master',
  'preset-image', 'remove-ai-watermark', 'seedance', 'storyboard-grid',
  'text-split', 'topaz-image-upscale', 'topaz-video-upscale', 'upload',
  // NodeDataMap 额外 4 项 (与 _node.tsx 对应的派生/容器类型)
  'idea_shortcut',
  'material-preview-section',
  'material-thumbnail',
  'audio-upload',
] as const;

export type NodeTypeKey = (typeof ALL_NODE_TYPES)[number];

/** 给定节点类型,返回其 data 形状 (Partial) */
export type NodeDataShape<T extends string> = T extends keyof NodeDataMap
  ? NodeDataMap[T]
  : Record<string, unknown>;

/** 给定节点类型,返回其 *强类型* 的 React Flow Node
 *  注:Node<T> 在 @xyflow/react 中要求 T extends Record<string, unknown>,
 *  但 NodeDataMap 的具体子类型 (IdeaNodeData 等) 并没有显式 index signature,
 *  故通过 `as unknown as Record<string, unknown>` 桥接 TS 的"strict index sig"检查。
 */
export type IMDFNode<T extends string> = Node<
  T extends keyof NodeDataMap
    ? (NodeDataMap[T] & Record<string, unknown>)
    : Record<string, unknown>
>;

// ─── IO 契约元数据 (用于审计/文档生成) ──────────────────────────────────────

export interface NodeIOContract {
  type: NodeTypeKey;
  label: string;
  /** 节点接收的输入 (上游) */
  inputs: Array<{
    name: string;
    type: 'text' | 'image' | 'video' | 'audio' | '3d' | 'string' | 'any';
    description: string;
  }>;
  /** 节点产出的输出 (下游) */
  outputs: Array<{
    name: string;
    type: 'text' | 'image' | 'video' | 'audio' | '3d' | 'string' | 'any';
    description: string;
  }>;
  /** 节点可配置的 data 字段 */
  configFields: Array<{
    name: string;
    type: 'string' | 'number' | 'boolean' | 'select' | 'json';
    required: boolean;
    description: string;
  }>;
}

export const NODE_IO_CONTRACTS: NodeIOContract[] = [
  {
    type: 'idea',
    label: '灵感节点',
    inputs: [],
    outputs: [
      { name: 'prompt', type: 'text', description: '灵感文本 → 拼接 title + content 后的 prompt' },
    ],
    configFields: [
      { name: 'title', type: 'string', required: false, description: '标题' },
      { name: 'content', type: 'string', required: false, description: '内容' },
    ],
  },
  {
    type: 'bp',
    label: 'BP 蓝图',
    inputs: [],
    outputs: [
      { name: 'prompt', type: 'text', description: '蓝图 prompt(标题 + 编号步骤)' },
    ],
    configFields: [
      { name: 'title', type: 'string', required: false, description: '项目标题' },
      { name: 'steps', type: 'json', required: false, description: '步骤列表 [{id,text,done}]' },
    ],
  },
  {
    type: 'text',
    label: '文本节点',
    inputs: [
      { name: 'upstream', type: 'any', description: '上游 @素材 引用' },
    ],
    outputs: [
      { name: 'prompt', type: 'text', description: '原始 prompt(含 @素材 符号)' },
      { name: 'promptResolved', type: 'text', description: '解析 @素材 后的纯文本' },
    ],
    configFields: [
      { name: 'prompt', type: 'string', required: false, description: '用户输入的 prompt' },
      { name: 'rhNodeId', type: 'string', required: false, description: '可选:RunningHub 节点序号绑定' },
    ],
  },
  {
    type: 'combine',
    label: '图像拼接',
    inputs: [
      { name: 'upstream', type: 'image', description: '至少 2 张上游图像' },
    ],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '拼接结果图' },
    ],
    configFields: [
      { name: 'direction', type: 'select', required: true, description: '拼接方向:horizontal | vertical' },
    ],
  },
  {
    type: 'resize',
    label: '尺寸调整',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游图像' },
    ],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '调整后图像' },
    ],
    configFields: [
      { name: 'width', type: 'number', required: true, description: '目标宽度 px' },
      { name: 'height', type: 'number', required: true, description: '目标高度 px' },
      { name: 'fit', type: 'select', required: true, description: '缩放模式: cover|contain|inside|fill' },
    ],
  },
  {
    type: 'upscale',
    label: '放大',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游图像' },
    ],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '放大后图像' },
    ],
    configFields: [
      { name: 'scale', type: 'select', required: true, description: '放大倍数: 1.5|2|3|4' },
    ],
  },
  {
    type: 'remove-bg',
    label: '抠图',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游图像' },
    ],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '抠图结果' },
    ],
    configFields: [],
  },
  {
    type: 'frame-extractor',
    label: '抽帧',
    inputs: [
      { name: 'upstream', type: 'video', description: '上游视频' },
    ],
    outputs: [
      { name: 'imageUrls', type: 'image', description: '抽帧后的图像列表' },
    ],
    configFields: [
      { name: 'interval', type: 'number', required: true, description: '抽帧间隔 (秒)' },
      { name: 'count', type: 'number', required: false, description: '最大抽帧数' },
    ],
  },
  {
    type: 'frame-pair',
    label: '首尾帧',
    inputs: [
      { name: 'upstream', type: 'video', description: '上游视频' },
    ],
    outputs: [
      { name: 'firstFrame', type: 'image', description: '首帧图' },
      { name: 'lastFrame', type: 'image', description: '尾帧图' },
    ],
    configFields: [],
  },
  {
    type: 'grid-crop',
    label: '宫格切图',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游图像' },
    ],
    outputs: [
      { name: 'imageUrls', type: 'image', description: '切割后的图像列表' },
    ],
    configFields: [
      { name: 'rows', type: 'number', required: true, description: '行数' },
      { name: 'cols', type: 'number', required: true, description: '列数' },
    ],
  },
  {
    type: 'grid-editor',
    label: '宫格拼图',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游图像' },
    ],
    outputs: [
      { name: 'imageUrls', type: 'image', description: '拼图结果' },
    ],
    configFields: [
      { name: 'rows', type: 'number', required: true, description: '行数' },
      { name: 'cols', type: 'number', required: true, description: '列数' },
    ],
  },
  {
    type: 'image',
    label: '图像生成',
    inputs: [
      { name: 'upstream', type: 'text', description: '上游 prompt 文本' },
      { name: 'upstream', type: 'image', description: '上游参考图' },
    ],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '主结果图' },
      { name: 'imageUrls', type: 'image', description: '多张结果图' },
    ],
    configFields: [
      { name: 'model', type: 'select', required: true, description: '模型 ID' },
      { name: 'ratio', type: 'select', required: false, description: '比例' },
      { name: 'size', type: 'select', required: false, description: '尺寸' },
      { name: 'n', type: 'number', required: false, description: '生成张数' },
    ],
  },
  {
    type: 'image-compare',
    label: '图像对比',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游图像' },
    ],
    outputs: [],
    configFields: [
      { name: 'leftUrl', type: 'string', required: false, description: '左图 URL' },
      { name: 'rightUrl', type: 'string', required: false, description: '右图 URL' },
    ],
  },
  {
    type: 'video',
    label: '视频生成',
    inputs: [
      { name: 'upstream', type: 'text', description: '上游 prompt 文本' },
      { name: 'upstream', type: 'image', description: '上游参考图' },
    ],
    outputs: [
      { name: 'videoUrl', type: 'video', description: '生成视频' },
    ],
    configFields: [
      { name: 'kind', type: 'select', required: true, description: '视频引擎: veo|grok|sora|seedance|kling|wan|minimax' },
      { name: 'model', type: 'string', required: false, description: '具体模型' },
      { name: 'ratio', type: 'string', required: false, description: '比例' },
      { name: 'duration', type: 'number', required: false, description: '时长(秒)' },
    ],
  },
  {
    type: 'video-output',
    label: '视频输出',
    inputs: [
      { name: 'upstream', type: 'video', description: '上游视频' },
    ],
    outputs: [
      { name: 'videoUrl', type: 'video', description: '透传视频' },
    ],
    configFields: [],
  },
  {
    type: 'audio',
    label: '音频生成',
    inputs: [
      { name: 'upstream', type: 'text', description: '上游 prompt 文本' },
    ],
    outputs: [
      { name: 'audioUrl', type: 'audio', description: '生成音频' },
    ],
    configFields: [
      { name: 'model', type: 'string', required: true, description: 'TTS 模型' },
      { name: 'voice', type: 'string', required: true, description: '音色' },
      { name: 'text', type: 'string', required: false, description: '要朗读的文本' },
    ],
  },
  {
    type: 'llm',
    label: '大模型',
    inputs: [
      { name: 'upstream', type: 'text', description: '上游 prompt 文本' },
    ],
    outputs: [
      { name: 'reply', type: 'text', description: '模型回复' },
      { name: 'outputText', type: 'text', description: 'outputText 字段透传' },
    ],
    configFields: [
      { name: 'model', type: 'string', required: true, description: 'LLM 模型' },
      { name: 'systemPrompt', type: 'string', required: false, description: '系统提示词' },
      { name: 'temperature', type: 'number', required: false, description: '温度' },
    ],
  },
  {
    type: 'loop',
    label: '循环',
    inputs: [],
    outputs: [],
    configFields: [
      { name: 'mode', type: 'select', required: true, description: '循环模式: for|while|map|reduce' },
      { name: 'count', type: 'number', required: false, description: '循环次数' },
    ],
  },
  {
    type: 'relay',
    label: '中继',
    inputs: [
      { name: 'upstream', type: 'any', description: '任意上游' },
    ],
    outputs: [
      { name: 'prompt', type: 'text', description: '透传文本' },
      { name: 'imageUrl', type: 'image', description: '透传图像' },
      { name: 'videoUrl', type: 'video', description: '透传视频' },
    ],
    configFields: [],
  },
  {
    type: 'output',
    label: '输出',
    inputs: [
      { name: 'upstream', type: 'any', description: '任意上游' },
    ],
    outputs: [
      { name: 'prompt', type: 'text', description: '收集的文本' },
      { name: 'imageUrls', type: 'image', description: '收集的图像' },
      { name: 'videoUrl', type: 'video', description: '收集的视频' },
    ],
    configFields: [],
  },
  {
    type: 'browser',
    label: '浏览器/抓取',
    inputs: [],
    outputs: [
      { name: 'response', type: 'text', description: '抓取响应文本' },
    ],
    configFields: [
      { name: 'url', type: 'string', required: true, description: '目标 URL' },
      { name: 'method', type: 'select', required: false, description: 'HTTP 方法' },
    ],
  },
  {
    type: 'placeholder',
    label: '占位节点',
    inputs: [],
    outputs: [],
    configFields: [
      { name: 'label', type: 'string', required: false, description: '显示标签' },
    ],
  },
  {
    type: 'aggregate-parser',
    label: '聚合解析',
    inputs: [],
    outputs: [
      { name: 'parsed', type: 'any', description: '解析后的字段' },
    ],
    configFields: [
      { name: 'url', type: 'string', required: true, description: '原始 URL' },
    ],
  },
  {
    type: 'comfy-ui-app-maker',
    label: 'ComfyUI 应用生成',
    inputs: [],
    outputs: [
      { name: 'outputImageUrl', type: 'image', description: '生成的应用封面/结果' },
    ],
    configFields: [
      { name: 'appId', type: 'string', required: true, description: 'ComfyUI 应用 ID' },
    ],
  },
  {
    type: 'comfy-ui-store',
    label: 'ComfyUI 应用商店',
    inputs: [],
    outputs: [
      { name: 'selectedAppId', type: 'string', description: '选中的应用 ID' },
    ],
    configFields: [
      { name: 'query', type: 'string', required: false, description: '搜索关键词' },
      { name: 'category', type: 'string', required: false, description: '分类' },
    ],
  },
  {
    type: 'running-hub',
    label: 'RunningHub',
    inputs: [],
    outputs: [
      { name: 'imageUrls', type: 'image', description: '生成结果图列表' },
    ],
    configFields: [
      { name: 'appId', type: 'string', required: true, description: 'RH 应用 ID' },
      { name: 'apiKey', type: 'string', required: false, description: 'RH API Key' },
    ],
  },
  {
    type: 'rh-config',
    label: 'RunningHub 配置',
    inputs: [],
    outputs: [],
    configFields: [
      { name: 'apiKey', type: 'string', required: true, description: 'RH API Key' },
      { name: 'baseUrl', type: 'string', required: false, description: 'RH base URL' },
      { name: 'maxConcurrent', type: 'number', required: false, description: '最大并发' },
    ],
  },
  {
    type: 'rh-tools',
    label: 'RunningHub 工具集',
    inputs: [],
    outputs: [
      { name: 'outputImageUrl', type: 'image', description: '输出图' },
    ],
    configFields: [
      { name: 'selectedAppId', type: 'string', required: true, description: '选中的应用 ID' },
    ],
  },
  {
    type: 'rh-toolbox',
    label: 'RunningHub 工具箱',
    inputs: [],
    outputs: [
      { name: 'outputImageUrl', type: 'image', description: '输出图' },
    ],
    configFields: [
      { name: 'toolId', type: 'string', required: true, description: '工具 ID' },
    ],
  },
  {
    type: 'fal-toolbox',
    label: 'FAL 工具箱',
    inputs: [],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '输出图' },
    ],
    configFields: [
      { name: 'modelId', type: 'string', required: true, description: 'FAL 模型 ID' },
    ],
  },
  {
    type: 'toolbox-param',
    label: '工具箱参数',
    inputs: [],
    outputs: [],
    configFields: [
      { name: 'params', type: 'json', required: false, description: '参数列表' },
    ],
  },
  {
    type: 'grok-oauth-agent',
    label: 'Grok OAuth 智能体',
    inputs: [],
    outputs: [
      { name: 'reply', type: 'text', description: '智能体回复' },
    ],
    configFields: [
      { name: 'model', type: 'string', required: true, description: 'Grok 模型' },
      { name: 'systemPrompt', type: 'string', required: false, description: '系统提示词' },
    ],
  },
  {
    type: 'group-box',
    label: '分组框',
    inputs: [],
    outputs: [],
    configFields: [
      { name: 'label', type: 'string', required: false, description: '分组标签' },
      { name: 'color', type: 'string', required: false, description: '分组颜色' },
    ],
  },
  {
    type: 'drawing-board',
    label: '画板',
    inputs: [],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '画板导出的图' },
    ],
    configFields: [
      { name: 'strokes', type: 'json', required: false, description: '笔画数据' },
    ],
  },
  {
    type: 'material-set',
    label: '素材集',
    inputs: [],
    outputs: [
      { name: 'selectedItemIds', type: 'any', description: '选中的素材 ID 列表' },
    ],
    configFields: [
      { name: 'kind', type: 'select', required: true, description: '素材类型: character|scene|prop|style|audio' },
      { name: 'items', type: 'json', required: false, description: '素材条目' },
    ],
  },
  {
    type: 'pick-from-set',
    label: '从素材集中挑选',
    inputs: [],
    outputs: [
      { name: 'selectedItem', type: 'any', description: '选中的素材' },
    ],
    configFields: [
      { name: 'setId', type: 'string', required: false, description: '上游素材集 ID' },
    ],
  },
  {
    type: 'portrait-metadata',
    label: '肖像元数据',
    inputs: [],
    outputs: [
      { name: 'prompt', type: 'text', description: '英文 prompt 模板' },
    ],
    configFields: [
      { name: 'name', type: 'string', required: false, description: '姓名' },
      { name: 'age', type: 'string', required: false, description: '年龄' },
      { name: 'gender', type: 'string', required: false, description: '性别' },
      { name: 'appearance', type: 'string', required: false, description: '外貌' },
      { name: 'outfit', type: 'string', required: false, description: '服饰' },
      { name: 'personality', type: 'string', required: false, description: '性格' },
      { name: 'background', type: 'string', required: false, description: '背景' },
    ],
  },
  {
    type: 'portrait-master',
    label: '肖像大师',
    inputs: [],
    outputs: [
      { name: 'prompt', type: 'text', description: '生成的 prompt' },
      { name: 'imageUrl', type: 'image', description: '生成图像' },
    ],
    configFields: [
      { name: 'presetId', type: 'string', required: true, description: '肖像预设 ID' },
      { name: 'viewId', type: 'string', required: false, description: '视角' },
    ],
  },
  {
    type: 'pose-master',
    label: '姿势大师',
    inputs: [],
    outputs: [
      { name: 'prompt', type: 'text', description: '姿势 prompt' },
      { name: 'imageUrl', type: 'image', description: '生成图像' },
    ],
    configFields: [
      { name: 'presetId', type: 'string', required: true, description: '姿势预设 ID' },
      { name: 'posePoints', type: 'json', required: false, description: '姿态点' },
    ],
  },
  {
    type: 'preset-image',
    label: '预设图像',
    inputs: [],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '预设图 URL' },
    ],
    configFields: [
      { name: 'presetId', type: 'string', required: true, description: '预设 ID' },
    ],
  },
  {
    type: 'remove-ai-watermark',
    label: 'AI 去水印',
    inputs: [],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '去水印图' },
      { name: 'videoUrl', type: 'video', description: '去水印视频' },
    ],
    configFields: [
      { name: 'sourceUrl', type: 'string', required: true, description: '原始 URL' },
    ],
  },
  {
    type: 'seedance',
    label: 'Seedance 即梦',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游参考图' },
      { name: 'upstream', type: 'text', description: '上游 prompt' },
    ],
    outputs: [
      { name: 'videoUrl', type: 'video', description: '生成视频' },
    ],
    configFields: [
      { name: 'mode', type: 'select', required: true, description: 'Seedance 模式: omni|first|firstlast|multiframe' },
      { name: 'duration', type: 'number', required: false, description: '时长(秒)' },
    ],
  },
  {
    type: 'storyboard-grid',
    label: '分镜宫格',
    inputs: [],
    outputs: [
      { name: 'imageUrls', type: 'image', description: '分镜图列表' },
    ],
    configFields: [
      { name: 'rows', type: 'number', required: true, description: '行数' },
      { name: 'cols', type: 'number', required: true, description: '列数' },
      { name: 'shots', type: 'json', required: false, description: '镜头列表' },
    ],
  },
  {
    type: 'text-split',
    label: '文本分段',
    inputs: [
      { name: 'upstream', type: 'text', description: '上游长文本' },
    ],
    outputs: [
      { name: 'chunks', type: 'text', description: '分段结果 (数组)' },
    ],
    configFields: [
      { name: 'separator', type: 'string', required: false, description: '分隔符,默认 \\n' },
      { name: 'maxChunkSize', type: 'number', required: false, description: '单段最大字符数' },
    ],
  },
  {
    type: 'topaz-image-upscale',
    label: 'Topaz 图像放大',
    inputs: [
      { name: 'upstream', type: 'image', description: '上游图像' },
    ],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '放大后图像' },
    ],
    configFields: [
      { name: 'scale', type: 'select', required: true, description: '放大倍数: 2|4|6' },
    ],
  },
  {
    type: 'topaz-video-upscale',
    label: 'Topaz 视频放大',
    inputs: [
      { name: 'upstream', type: 'video', description: '上游视频' },
    ],
    outputs: [
      { name: 'videoUrl', type: 'video', description: '放大后视频' },
    ],
    configFields: [
      { name: 'scale', type: 'select', required: true, description: '放大倍数: 2|4' },
    ],
  },
  {
    type: 'upload',
    label: '上传',
    inputs: [],
    outputs: [
      { name: 'imageUrl', type: 'image', description: '上传的图像' },
      { name: 'imageUrls', type: 'image', description: '多张上传图' },
      { name: 'videoUrl', type: 'video', description: '上传的视频' },
    ],
    configFields: [
      { name: 'files', type: 'json', required: false, description: '已上传文件列表' },
    ],
  },
];
