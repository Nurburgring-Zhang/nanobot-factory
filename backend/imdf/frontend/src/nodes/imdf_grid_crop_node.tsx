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
 * 类型 key : grid-crop
 * 组件     : GridCropNode
 * Data in  : NodeDataShape<'grid-crop'> (用户/上游配置 + 节点自身状态)
 * Data out : imageUrl/videoUrl/audioUrl/prompt/outputText 写回 data
 * 默认值   : mergeDefaultData('grid-crop', p.data) → defaults.ts
 * IO 文档   : NODE_IO_CONTRACTS → 类型 'grid-crop'
 * onChange : useUpdateNodeData(id).update(patch) 浅合并到 data
 * ────────────────────────────────────────────────────────────────────
 */


import { memo, useEffect, useMemo, useState } from 'react';
import { Grid3x3 } from 'lucide-react';
import type { NodeProps } from '@xyflow/react';
import { ImageOpFrame } from './ImageOpFrame';
import { useUpdateNodeData } from './useUpdateNodeData';
import { useUpstreamMaterials } from './useUpstreamMaterials';
import { opGridCrop } from '../../services/imageOps';

const clampInt = (value: any, min: number, max: number, fallback: number) => {
  const n = Number.parseInt(String(value), 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
};

const GRID_PRESETS = [
  { label: '2×2', rows: 2, cols: 2 },
  { label: '3×3', rows: 3, cols: 3 },
  { label: '2×3', rows: 2, cols: 3 },
  { label: '1×4', rows: 1, cols: 4 },
  { label: '4×1', rows: 4, cols: 1 },
];

type GridOrderMode = 'row' | 'column' | 'snake' | 'reverse';

const GRID_ORDER_OPTIONS: Array<{ value: GridOrderMode; label: string; hint: string }> = [
  { value: 'row', label: '行优先', hint: '1→2→3' },
  { value: 'column', label: '列优先', hint: '1↓4↓7' },
  { value: 'snake', label: '蛇形', hint: '适合分镜' },
  { value: 'reverse', label: '反向', hint: '倒序输出' },
];

const normalizeOrderMode = (value: any): GridOrderMode => {
  if (value === 'column' || value === 'snake' || value === 'reverse') return value;
  return 'row';
};

const buildOrderedCells = (rows: number, cols: number, mode: GridOrderMode) => {
  const cells: Array<{ row: number; col: number }> = [];
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) cells.push({ row, col });
  }
  if (mode === 'column') return cells.sort((a, b) => (a.col - b.col) || (a.row - b.row));
  if (mode === 'snake') {
    return cells.sort((a, b) => {
      if (a.row !== b.row) return a.row - b.row;
      const ac = a.row % 2 === 0 ? a.col : -a.col;
      const bc = b.row % 2 === 0 ? b.col : -b.col;
      return ac - bc;
    });
  }
  if (mode === 'reverse') return cells.sort((a, b) => (b.row - a.row) || (b.col - a.col));
  return cells.sort((a, b) => (a.row - b.row) || (a.col - b.col));
};

const parseExportIndexes = (value: any, total: number): number[] => {
  const raw = String(value || '').trim();
  if (!raw) return [];
  const set = new Set<number>();
  for (const part of raw.split(/[,\s，、]+/)) {
    const token = part.trim();
    if (!token) continue;
    const range = token.match(/^(\d+)\s*[-~至]\s*(\d+)$/);
    if (range) {
      const a = Number.parseInt(range[1], 10);
      const b = Number.parseInt(range[2], 10);
      const start = Math.max(1, Math.min(a, b));
      const end = Math.min(total, Math.max(a, b));
      for (let i = start; i <= end; i++) set.add(i);
      continue;
    }
    const n = Number.parseInt(token, 10);
    if (Number.isFinite(n) && n >= 1 && n <= total) set.add(n);
  }
  return Array.from(set).sort((a, b) => a - b);
};

const loadImageNaturalSize = (src: string) =>
  new Promise<{ w: number; h: number }>((resolve, reject) => {
    const img = new window.Image();
    img.onload = () => resolve({ w: img.naturalWidth || 1, h: img.naturalHeight || 1 });
    img.onerror = () => reject(new Error('无法读取上游图像尺寸'));
    img.src = src;
  });

const makeRectFromCell = (
  cell: { row: number; col: number },
  naturalW: number,
  naturalH: number,
  rows: number,
  cols: number,
  gap: number,
) => {
  const halfGap = gap / 2;
  const topLine = (cell.row * naturalH) / rows;
  const bottomLine = ((cell.row + 1) * naturalH) / rows;
  const leftLine = (cell.col * naturalW) / cols;
  const rightLine = ((cell.col + 1) * naturalW) / cols;
  const y1 = Math.round(cell.row === 0 ? 0 : topLine + halfGap);
  const y2 = Math.round(cell.row === rows - 1 ? naturalH : bottomLine - halfGap);
  const x1 = Math.round(cell.col === 0 ? 0 : leftLine + halfGap);
  const x2 = Math.round(cell.col === cols - 1 ? naturalW : rightLine - halfGap);
  if (x2 <= x1 || y2 <= y1) return null;
  return {
    row: cell.row,
    col: cell.col,
    x: x1,
    y: y1,
    w: x2 - x1,
    h: y2 - y1,
  };
};

interface GridPreviewProps {
  imageUrl?: string;
  imageCount: number;
  rows: number;
  cols: number;
  gap: number;
  orderMode: GridOrderMode;
  exportIndexes: number[];
  hasExportFilter: boolean;
}

const GridPreview = ({ imageUrl, imageCount, rows, cols, gap, orderMode, exportIndexes, hasExportFilter }: GridPreviewProps) => {
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    setNaturalSize(null);
  }, [imageUrl]);

  const lines = useMemo(() => {
    if (!naturalSize) return [];
    const next: Array<{ type: 'h' | 'v'; pos: number }> = [];
    for (let i = 1; i < rows; i++) next.push({ type: 'h', pos: (i * naturalSize.h) / rows });
    for (let i = 1; i < cols; i++) next.push({ type: 'v', pos: (i * naturalSize.w) / cols });
    return next;
  }, [cols, naturalSize, rows]);

  const cellLabels = useMemo(() => {
    if (!naturalSize) return [];
    const ordered = buildOrderedCells(rows, cols, orderMode);
    const selectedSet = new Set(exportIndexes);
    return ordered.map((cell, index) => {
      const label = index + 1;
      const x = ((cell.col + 0.5) * naturalSize.w) / cols;
      const y = ((cell.row + 0.5) * naturalSize.h) / rows;
      const active = !hasExportFilter || selectedSet.has(label);
      return { ...cell, label, x, y, active };
    });
  }, [cols, exportIndexes, hasExportFilter, naturalSize, orderMode, rows]);

  if (!imageUrl) {
    return (
      <div className="col-span-2 rounded-lg border border-dashed border-white/15 bg-white/5 px-3 py-4 text-center text-[11px] text-white/40">
        连接上游图像后显示切线和去缝预览
      </div>
    );
  }

  return (
    <div className="col-span-2 rounded-lg border border-white/10 bg-black/20 p-1.5">
      <div className="flex justify-center rounded bg-black/25 p-1">
        <div className="relative inline-block max-w-full overflow-hidden rounded" style={{ lineHeight: 0 }}>
          <img
            src={imageUrl}
            alt="宫格剪裁预览"
            draggable={false}
            onLoad={(e) => {
              const img = e.currentTarget;
              setNaturalSize({ w: img.naturalWidth || 1, h: img.naturalHeight || 1 });
            }}
            className="block max-h-44 max-w-full object-contain"
          />
          {naturalSize && (
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox={`0 0 ${naturalSize.w} ${naturalSize.h}`}
              preserveAspectRatio="none"
            >
              {gap > 0 &&
                lines.map((line, index) => {
                  const half = gap / 2;
                  if (line.type === 'h') {
                    const y = Math.max(0, line.pos - half);
                    const h = Math.min(gap, naturalSize.h - y);
                    return (
                      <rect
                        key={`gap-h-${index}`}
                        x={0}
                        y={y}
                        width={naturalSize.w}
                        height={h}
                        fill="#fb923c"
                        opacity={0.28}
                      />
                    );
                  }
                  const x = Math.max(0, line.pos - half);
                  const w = Math.min(gap, naturalSize.w - x);
                  return (
                    <rect
                      key={`gap-v-${index}`}
                      x={x}
                      y={0}
                      width={w}
                      height={naturalSize.h}
                      fill="#fb923c"
                      opacity={0.28}
                    />
                  );
                })}
              {lines.map((line, index) => {
                const half = gap / 2;
                if (line.type === 'h') {
                  return (
                    <g key={`line-h-${index}`}>
                      <line x1={0} x2={naturalSize.w} y1={line.pos} y2={line.pos} stroke="#111827" strokeWidth={4} opacity={0.55} />
                      <line x1={0} x2={naturalSize.w} y1={line.pos} y2={line.pos} stroke="#fb923c" strokeWidth={2.2} />
                      {gap > 0 && (
                        <>
                          <line x1={0} x2={naturalSize.w} y1={line.pos - half} y2={line.pos - half} stroke="#fff7ed" strokeWidth={1.2} strokeDasharray="10 7" opacity={0.9} />
                          <line x1={0} x2={naturalSize.w} y1={line.pos + half} y2={line.pos + half} stroke="#fff7ed" strokeWidth={1.2} strokeDasharray="10 7" opacity={0.9} />
                        </>
                      )}
                    </g>
                  );
                }
                return (
                  <g key={`line-v-${index}`}>
                    <line x1={line.pos} x2={line.pos} y1={0} y2={naturalSize.h} stroke="#111827" strokeWidth={4} opacity={0.55} />
                    <line x1={line.pos} x2={line.pos} y1={0} y2={naturalSize.h} stroke="#fb923c" strokeWidth={2.2} />
                    {gap > 0 && (
                      <>
                        <line x1={line.pos - half} x2={line.pos - half} y1={0} y2={naturalSize.h} stroke="#fff7ed" strokeWidth={1.2} strokeDasharray="10 7" opacity={0.9} />
                        <line x1={line.pos + half} x2={line.pos + half} y1={0} y2={naturalSize.h} stroke="#fff7ed" strokeWidth={1.2} strokeDasharray="10 7" opacity={0.9} />
                      </>
                    )}
                  </g>
                );
              })}
              {cellLabels.map((cell) => (
                <g key={`cell-${cell.row}-${cell.col}`} opacity={cell.active ? 0.95 : 0.25}>
                  <circle
                    cx={cell.x}
                    cy={cell.y}
                    r={Math.max(12, Math.min(naturalSize.w / cols, naturalSize.h / rows) * 0.1)}
                    fill={cell.active ? '#fb923c' : '#111827'}
                    stroke="#fff7ed"
                    strokeWidth={1.4}
                  />
                  <text
                    x={cell.x}
                    y={cell.y + 4}
                    textAnchor="middle"
                    fontSize={Math.max(11, Math.min(naturalSize.w / cols, naturalSize.h / rows) * 0.09)}
                    fontWeight={700}
                    fill="#fff7ed"
                    style={{ paintOrder: 'stroke', stroke: '#111827', strokeWidth: 2 }}
                  >
                    {cell.label}
                  </text>
                </g>
              ))}
            </svg>
          )}
        </div>
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-white/40">
        <span>预览第 1 张上游图像</span>
        <span>
          {imageCount > 1 ? `共 ${imageCount} 张 · ` : ''}
          {rows}×{cols}
          {gap > 0 ? ` · 去缝 ${gap}px` : ''}
        </span>
      </div>
    </div>
  );
};

const GridCropNode = (p: NodeProps) => {
  const update = useUpdateNodeData(p.id);
  const upstream = useUpstreamMaterials(p.id);
  const d = mergeDefaultData('grid-crop', (p.data as Partial<NodeDataShape<'grid-crop'>>) || undefined);
  const rows = clampInt(d?.rows, 1, 20, 3);
  const cols = clampInt(d?.cols, 1, 20, 3);
  const gap = clampInt(d?.gap, 0, 240, 0);
  const orderMode = normalizeOrderMode(d?.orderMode);
  const exportIndexText = typeof d?.exportIndexText === 'string' ? d.exportIndexText : '';
  const batchMode: 'first' | 'all' = d?.batchMode === 'all' ? 'all' : 'first';
  const inputImages = upstream.images.map((item) => item.url);
  const previewUrl = inputImages[0];
  const totalTiles = rows * cols;
  const exportIndexes = parseExportIndexes(exportIndexText, totalTiles);
  const hasExportFilter = exportIndexText.trim().length > 0;
  const exportCount = hasExportFilter ? exportIndexes.length : totalTiles;
  const sourceCount = batchMode === 'all' ? Math.max(1, inputImages.length) : 1;
  const outputCount = Math.max(0, exportCount * sourceCount);
  const orderLabel = GRID_ORDER_OPTIONS.find((item) => item.value === orderMode)?.label || '行优先';
  return (
    <ImageOpFrame
      id={p.id}
      data={p.data}
      selected={p.selected}
      title="宫格剪裁"
      subtitle={`${rows}×${cols}${gap > 0 ? ` · 去缝 ${gap}px` : ''} · ${orderLabel}`}
      icon={<Grid3x3 size={13} />}
      colorHex="#fb923c"
      bgRgba="rgba(251,146,60,.2)"
      shadowRgba="rgba(251,146,60,.2)"
      textHex="#fed7aa"
      buttonClasses="bg-orange-500/20 hover:bg-orange-500/30 text-orange-200"
      renderSettings={() => (
        <div className="grid grid-cols-2 gap-2">
          <GridPreview
            imageUrl={previewUrl}
            imageCount={inputImages.length}
            rows={rows}
            cols={cols}
            gap={gap}
            orderMode={orderMode}
            exportIndexes={exportIndexes}
            hasExportFilter={hasExportFilter}
          />
          <div>
            <label className="text-[10px] text-white/50 block mb-1">行</label>
            <input
              type="number"
              min={1}
              max={20}
              value={rows}
              onChange={(e) => update({ rows: clampInt(e.target.value, 1, 20, 3) })}
              className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
            />
          </div>
          <div>
            <label className="text-[10px] text-white/50 block mb-1">列</label>
            <input
              type="number"
              min={1}
              max={20}
              value={cols}
              onChange={(e) => update({ cols: clampInt(e.target.value, 1, 20, 3) })}
              className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
            />
          </div>
          <div className="col-span-2">
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-white/50">去缝间距</label>
              <span className="text-[10px] text-white/40">{gap}px</span>
            </div>
            <div className="grid grid-cols-[1fr_56px] gap-2">
              <input
                type="range"
                min={0}
                max={240}
                value={gap}
                onChange={(e) => update({ gap: clampInt(e.target.value, 0, 240, 0) })}
                className="w-full accent-orange-400"
              />
              <input
                type="number"
                min={0}
                max={240}
                value={gap}
                onChange={(e) => update({ gap: clampInt(e.target.value, 0, 240, 0) })}
                className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
              />
            </div>
            <div className="mt-1 text-[10px] text-white/35">用于裁掉宫格线、拼图缝或截图留白边缘</div>
          </div>
          <div className="col-span-2 grid grid-cols-5 gap-1">
            {GRID_PRESETS.map((preset) => {
              const active = rows === preset.rows && cols === preset.cols;
              return (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => update({ rows: preset.rows, cols: preset.cols })}
                  className={`py-1 rounded text-[10px] transition-colors border ${
                    active
                      ? 'bg-orange-500/30 text-orange-100 border-orange-400/40'
                      : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10'
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
          <div className="col-span-2 grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] text-white/50 block mb-1">输出顺序</label>
              <select
                value={orderMode}
                onChange={(e) => update({ orderMode: normalizeOrderMode(e.target.value) })}
                className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
              >
                {GRID_ORDER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="mt-1 text-[10px] text-white/35">
                {GRID_ORDER_OPTIONS.find((item) => item.value === orderMode)?.hint}
              </div>
            </div>
            <div>
              <label className="text-[10px] text-white/50 block mb-1">导出序号</label>
              <input
                type="text"
                value={exportIndexText}
                onChange={(e) => update({ exportIndexText: e.target.value })}
                placeholder="留空全部，如 1,3,5-8"
                className="w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/30"
              />
              <div className={`mt-1 text-[10px] ${hasExportFilter && exportIndexes.length === 0 ? 'text-red-300' : 'text-white/35'}`}>
                {hasExportFilter
                  ? exportIndexes.length > 0
                    ? `本图导出 ${exportIndexes.join(', ')}`
                    : `可选范围 1-${totalTiles}`
                  : '按当前顺序导出全部'}
              </div>
            </div>
          </div>
          <div className="col-span-2 flex items-center justify-between gap-2 rounded border border-white/10 bg-white/5 px-2 py-1.5">
            <label className="flex min-w-0 items-center gap-2 text-[11px] text-white/70">
              <input
                type="checkbox"
                checked={batchMode === 'all'}
                onChange={(e) => update({ batchMode: e.target.checked ? 'all' : 'first' })}
                className="accent-orange-400"
              />
              <span>上游合集批量拆分</span>
            </label>
            <span className="shrink-0 text-[10px] text-white/40">
              {batchMode === 'all'
                ? `${inputImages.length || 0} 张 × ${exportCount || 0} = ${outputCount || 0}`
                : `${exportCount || 0} 项`}
            </span>
          </div>
        </div>
      )}
      inputImages={inputImages}
      processAllInputs={batchMode === 'all'}
      width={320}
      runOp={async (img) => {
        if (hasExportFilter && exportIndexes.length === 0) {
          throw new Error(`导出序号无效，可选范围 1-${totalTiles}`);
        }
        const size = await loadImageNaturalSize(img as string);
        const selectedSet = new Set(exportIndexes);
        const cells = buildOrderedCells(rows, cols, orderMode).filter((_, index) =>
          !hasExportFilter || selectedSet.has(index + 1)
        );
        const rects = cells
          .map((cell) => makeRectFromCell(cell, size.w, size.h, rows, cols, gap))
          .filter((rect): rect is { x: number; y: number; w: number; h: number; row: number; col: number } => Boolean(rect));
        if (rects.length === 0) throw new Error('无有效切割矩形，请调小去缝间距或检查导出序号');
        return opGridCrop(img as string, rows, cols, gap, rects, { orderMode });
      }}
    />
  );
};

export default memo(GridCropNode);
