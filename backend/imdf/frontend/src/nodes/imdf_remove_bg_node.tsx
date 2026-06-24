import type { NodeDataShape } from './types';
import { mergeDefaultData } from './defaults';

/**
 * IMDF Migration — from penguin-canvas (T8mars)
 * Source: /mnt/d/Hermes/imdf_vendor/penguin-canvas/src/components/nodes/
 * Renamed: PascalCase -> snake_case
 * This file is a physical copy; no logic has been rewritten.
 */

/**
 * ─── R3-Worker-4 IO CONTRACT MARKER ────────────────────────────────
 * 类型 key : remove-bg
 * 组件     : RemoveBgNode
 * Data in  : NodeDataShape<'remove-bg'> (用户/上游配置 + 节点自身状态)
 * Data out : imageUrl/videoUrl/audioUrl/prompt/outputText 写回 data
 * 默认值   : mergeDefaultData('remove-bg', p.data) → defaults.ts
 * IO 文档   : NODE_IO_CONTRACTS → 类型 'remove-bg'
 * onChange : useUpdateNodeData(id).update(patch) 浅合并到 data
 * ────────────────────────────────────────────────────────────────────
 */


import { memo } from 'react';
import { Scissors } from 'lucide-react';
import type { NodeProps } from '@xyflow/react';
import { ImageOpFrame } from './ImageOpFrame';
import { opRemoveBg } from '../../services/imageOps';

/**
 * RemoveBgNode - 抠图(占位实现,后端会返回原图 + warning)
 * 后续可接入第三方抠图服务
 */
const RemoveBgNode = (p: NodeProps) => {
  // 数据包合并: 节点自身不持有 data,ImageOpFrame 负责代理; 这里
  // 调用 mergeDefaultData 以保持与其它节点一致的 IO 契约 (mergeDefaultData
  // 的 'remove-bg' 默认值为空对象, 不会污染下游)
  mergeDefaultData('remove-bg', (p.data as Partial<NodeDataShape<'remove-bg'>>) || undefined);
  return (
    <ImageOpFrame
      id={p.id}
      data={p.data}
      selected={p.selected}
      title="抠图"
      subtitle="移除背景"
      icon={<Scissors size={13} />}
      colorHex="#fb923c"
      bgRgba="rgba(251,146,60,.2)"
      shadowRgba="rgba(251,146,60,.2)"
      textHex="#fed7aa"
      buttonClasses="bg-orange-500/20 hover:bg-orange-500/30 text-orange-200"
      renderSettings={() => (
        <div className="text-[10px] text-white/40 px-1 py-0.5 leading-relaxed">
          ⚠ 占位实现 - 当前仅转 PNG 输出,后续接入抠图服务
        </div>
      )}
      runOp={async (img) => opRemoveBg(img as string)}
    />
  );
};

export default memo(RemoveBgNode);
