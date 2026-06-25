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
 * 类型 key : resize
 * 组件     : ResizeNode
 * Data in  : NodeDataShape<'resize'> (用户/上游配置 + 节点自身状态)
 * Data out : imageUrl/videoUrl/audioUrl/prompt/outputText 写回 data
 * 默认值   : mergeDefaultData('resize', p.data) → defaults.ts
 * IO 文档   : NODE_IO_CONTRACTS → 类型 'resize'
 * onChange : useUpdateNodeData(id).update(patch) 浅合并到 data
 * ────────────────────────────────────────────────────────────────────
 */


import { memo } from 'react';
import { Maximize2 } from 'lucide-react';
import type { NodeProps } from '@xyflow/react';
import { ImageOpFrame } from './ImageOpFrame';
import { useUpdateNodeData } from './useUpdateNodeData';
import { opResize } from '../../services/imageOps';

const ResizeNode = (p: NodeProps) => {
  const update = useUpdateNodeData(p.id);
  const d = mergeDefaultData('resize', (p.data as Partial<NodeDataShape<'resize'>>) || undefined);
  const width = d?.width || 1024;
  const height = d?.height || 1024;
  // 默认 fit=cover：裁剪銘满到精确目标尺寸，符合“尺寸调整”的直觉语义。
  // 老存档中 d?.fit==='inside' 仍会保留以避免破坏序列化，用户可手动改。
  const fit = d?.fit || 'cover';
  // fit 选项中文说明（sharp 语义）：
  //   cover   覆盖：裁剪銘满 · 保比例（推荐，输出严格 W×H）
  //   contain 包含：留白銘填 · 保比例（输出严格 W×H）
  //   inside  限制内：不超 W×H · 保比例（输出不一定 W×H，是“不裁剪”模式）
  //   fill    填充：拉伸到 W×H · 可能变形
  const FIT_OPTIONS: Array<{ v: string; label: string }> = [
    { v: 'cover', label: 'cover · 裁剪銘满（保比例）' },
    { v: 'contain', label: 'contain · 包含留白（保比例）' },
    { v: 'inside', label: 'inside · 不超尺寸（不裁剪）' },
    { v: 'fill', label: 'fill · 拉伸填充（可变形）' },
  ];
  return (
    <ImageOpFrame
      id={p.id}
      data={p.data}
      selected={p.selected}
      title="尺寸调整"
      subtitle={`${width}×${height} · ${fit}`}
      icon={<Maximize2 size={13} />}
      colorHex="#fb923c"
      bgRgba="rgba(251,146,60,.2)"
      shadowRgba="rgba(251,146,60,.2)"
      textHex="#fed7aa"
      buttonClasses="bg-orange-500/20 hover:bg-orange-500/30 text-orange-200"
      renderSettings={() => (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-white/50 block mb-1">宽</label>
            <input
              type="number"
              value={width}
              onChange={(e) => update({ width: parseInt(e.target.value) || 0 })}
              className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
            />
          </div>
          <div>
            <label className="text-[10px] text-white/50 block mb-1">高</label>
            <input
              type="number"
              value={height}
              onChange={(e) => update({ height: parseInt(e.target.value) || 0 })}
              className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
            />
          </div>
          <div className="col-span-2">
            <label className="text-[10px] text-white/50 block mb-1">Fit</label>
            <select
              value={fit}
              onChange={(e) => update({ fit: e.target.value })}
              className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
            >
              {FIT_OPTIONS.map((x) => (
                <option key={x.v} value={x.v} className="bg-zinc-900">
                  {x.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
      runOp={async (img) => opResize(img as string, width, height, fit)}
    />
  );
};

export default memo(ResizeNode);
