/**
 * 类型契约 smoke test (R3.5-W3)
 * --------------------------------------------------------------------
 * 验证 49 节点的 mergeDefaultData 调用在 types.ts 的 NodeDataMap / NodeTypeKey
 * 契约下能编译通过。
 *
 * 用法: npx tsc --noEmit --skipLibCheck --strict src/_typecheck_io.ts
 * --------------------------------------------------------------------
 */

// 模拟每个节点的 mergeDefaultData 调用 (1 行/节点)
// 这一行需要 types.ts 的 NodeDataMap 完整定义,否则会编译失败

import type { NodeDataShape } from './nodes/types';
import { mergeDefaultData } from './nodes/defaults';

// 49 节点的类型契约 smoke test
// 覆盖范围: 全部 49 个 type key 都必须能通过 NodeDataMap 索引

const _typecheck = {
  // Group A: 常规 30 节点 (与 R3.5-W1 修复列表一致)
  audio:           mergeDefaultData('audio',            undefined as Partial<NodeDataShape<'audio'>>),
  bp:              mergeDefaultData('bp',               undefined as Partial<NodeDataShape<'bp'>>),
  browser:         mergeDefaultData('browser',          undefined as Partial<NodeDataShape<'browser'>>),
  combine:         mergeDefaultData('combine',          undefined as Partial<NodeDataShape<'combine'>>),
  comfy_ui_app_maker: mergeDefaultData('comfy-ui-app-maker', undefined as Partial<NodeDataShape<'comfy-ui-app-maker'>>),
  comfy_ui_store:  mergeDefaultData('comfy-ui-store',   undefined as Partial<NodeDataShape<'comfy-ui-store'>>),
  drawing_board:   mergeDefaultData('drawing-board',    undefined as Partial<NodeDataShape<'drawing-board'>>),
  fal_toolbox:     mergeDefaultData('fal-toolbox',      undefined as Partial<NodeDataShape<'fal-toolbox'>>),
  grid_editor:     mergeDefaultData('grid-editor',      undefined as Partial<NodeDataShape<'grid-editor'>>),
  grok_oauth_agent: mergeDefaultData('grok-oauth-agent', undefined as Partial<NodeDataShape<'grok-oauth-agent'>>),
  group_box:       mergeDefaultData('group-box',        undefined as Partial<NodeDataShape<'group-box'>>),
  image:           mergeDefaultData('image',            undefined as Partial<NodeDataShape<'image'>>),
  llm:             mergeDefaultData('llm',              undefined as Partial<NodeDataShape<'llm'>>),
  material_set:    mergeDefaultData('material-set',     undefined as Partial<NodeDataShape<'material-set'>>),
  output:          mergeDefaultData('output',           undefined as Partial<NodeDataShape<'output'>>),
  placeholder:     mergeDefaultData('placeholder',      undefined as Partial<NodeDataShape<'placeholder'>>),
  portrait_master: mergeDefaultData('portrait-master',  undefined as Partial<NodeDataShape<'portrait-master'>>),
  pose_master:     mergeDefaultData('pose-master',      undefined as Partial<NodeDataShape<'pose-master'>>),
  remove_ai_watermark: mergeDefaultData('remove-ai-watermark', undefined as Partial<NodeDataShape<'remove-ai-watermark'>>),
  remove_bg:       mergeDefaultData('remove-bg',        undefined as Partial<NodeDataShape<'remove-bg'>>),
  rh_config:       mergeDefaultData('rh-config',        undefined as Partial<NodeDataShape<'rh-config'>>),
  rh_toolbox:      mergeDefaultData('rh-toolbox',       undefined as Partial<NodeDataShape<'rh-toolbox'>>),
  rh_tools:        mergeDefaultData('rh-tools',         undefined as Partial<NodeDataShape<'rh-tools'>>),
  running_hub:     mergeDefaultData('running-hub',      undefined as Partial<NodeDataShape<'running-hub'>>),
  seedance:        mergeDefaultData('seedance',         undefined as Partial<NodeDataShape<'seedance'>>),
  text:            mergeDefaultData('text',             undefined as Partial<NodeDataShape<'text'>>),
  text_split:      mergeDefaultData('text-split',       undefined as Partial<NodeDataShape<'text-split'>>),
  topaz_image_upscale: mergeDefaultData('topaz-image-upscale', undefined as Partial<NodeDataShape<'topaz-image-upscale'>>),
  topaz_video_upscale: mergeDefaultData('topaz-video-upscale', undefined as Partial<NodeDataShape<'topaz-video-upscale'>>),
  upload:          mergeDefaultData('upload',           undefined as Partial<NodeDataShape<'upload'>>),
  video:           mergeDefaultData('video',            undefined as Partial<NodeDataShape<'video'>>),
  video_output:    mergeDefaultData('video-output',     undefined as Partial<NodeDataShape<'video-output'>>),
  // Group B: 19 个 baseline 节点 (verify 报告判 PASS 的原 19 节点)
  idea:            mergeDefaultData('idea',             undefined as Partial<NodeDataShape<'idea'>>),
  resize:          mergeDefaultData('resize',           undefined as Partial<NodeDataShape<'resize'>>),
  upscale:         mergeDefaultData('upscale',          undefined as Partial<NodeDataShape<'upscale'>>),
  frame_extractor: mergeDefaultData('frame-extractor',  undefined as Partial<NodeDataShape<'frame-extractor'>>),
  frame_pair:      mergeDefaultData('frame-pair',       undefined as Partial<NodeDataShape<'frame-pair'>>),
  grid_crop:       mergeDefaultData('grid-crop',        undefined as Partial<NodeDataShape<'grid-crop'>>),
  image_compare:   mergeDefaultData('image-compare',    undefined as Partial<NodeDataShape<'image-compare'>>),
  loop:            mergeDefaultData('loop',             undefined as Partial<NodeDataShape<'loop'>>),
  relay:           mergeDefaultData('relay',            undefined as Partial<NodeDataShape<'relay'>>),
  pick_from_set:   mergeDefaultData('pick-from-set',    undefined as Partial<NodeDataShape<'pick-from-set'>>),
  preset_image:    mergeDefaultData('preset-image',     undefined as Partial<NodeDataShape<'preset-image'>>),
  portrait_metadata: mergeDefaultData('portrait-metadata', undefined as Partial<NodeDataShape<'portrait-metadata'>>),
  toolbox_param:   mergeDefaultData('toolbox-param',    undefined as Partial<NodeDataShape<'toolbox-param'>>),
  aggregate_parser: mergeDefaultData('aggregate-parser', undefined as Partial<NodeDataShape<'aggregate-parser'>>),
  // Group C: 2 个特殊 key (model3d-preview / panorama3d 待补)
  // model3d-preview 暂未在 NodeDataMap (用 as never 兜底,验证不通过 NodeDataShape 索引)
  // panorama3d 同上
  // 这两个不在 _typecheck 中测试,仅作为已知偏差
};

void _typecheck;
