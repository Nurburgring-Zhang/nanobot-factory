/**
 * R3.5-W2 stub: 素材集节点数据生成
 */

import type { MaterialSetKind, MaterialSetItem } from '../services/api';

export type { MaterialSetKind, MaterialSetItem };

export function materialSetItemsToData(
  kind: MaterialSetKind,
  items: MaterialSetItem[]
): Record<string, unknown> {
  return {
    materialSetKind: kind,
    materialSetItems: items,
    itemCount: items.length,
  };
}
