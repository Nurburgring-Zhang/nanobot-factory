/**
 * useHasAutoOutput — 检测节点是否已有下游自动输出节点 (R3-Worker-4)
 * (新文件 — 之前 50 个节点都 import 它但不存在)
 * --------------------------------------------------------------------
 */

import { useReactFlow } from '@xyflow/react';

export function useHasAutoOutput(nodeId: string): boolean {
  const { getEdges, getNodes } = useReactFlow();
  const edges = getEdges();
  const nodes = getNodes();
  const downstreamIds = edges.filter((e) => e.source === nodeId).map((e) => e.target);
  for (const did of downstreamIds) {
    const dn = nodes.find((n) => n.id === did);
    if (dn && ['output', 'video-output', 'image-compare', 'preset-image'].includes(dn.type ?? '')) {
      return true;
    }
  }
  return false;
}
