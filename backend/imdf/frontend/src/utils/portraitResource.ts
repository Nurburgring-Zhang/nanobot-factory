/**
 * R3.5-W2 stub: 人像资源 → 节点数据
 */

import type { ResourceItem } from '../services/api';

export function portraitResourceToNodeData(
  item: ResourceItem
): Record<string, unknown> | null {
  if (item.kind !== 'portrait' && item.kind !== 'image') return null;
  return {
    kind: 'portrait-master',
    imageUrl: item.fileUrl,
    fileName: item.title ?? item.originalName ?? 'portrait',
    sourceResourceId: item.id,
  };
}
