/**
 * useUpdateNodeData — 写回 xyflow 节点 data 的 hook (R3-Worker-4)
 * --------------------------------------------------------------------
 * 之前所有 50 个 _node.tsx 节点都从 './useUpdateNodeData' 导入此 hook,
 * 但实际文件不存在,导致整个 imdf-app 永远无法构建。
 *
 * 本实现基于 @xyflow/react v12 的 useReactFlow().setNodes() API,
 * 浅合并传入的 patch 到对应节点 data 上,触发一次强制更新。
 * --------------------------------------------------------------------
 */

import { useCallback, useMemo } from 'react';
import { useReactFlow } from '@xyflow/react';

export type NodeDataPatch = Record<string, unknown>;

/**
 * 写回节点 data 的 hook。
 * @param nodeId 目标节点 id
 * @returns update(patch): 浅合并 patch 到 data 并触发更新
 */
export function useUpdateNodeData(nodeId: string) {
  const { setNodes } = useReactFlow();

  return useCallback(
    (patch: NodeDataPatch) => {
      setNodes((nodes) =>
        nodes.map((n) =>
          n.id === nodeId
            ? { ...n, data: { ...(n.data as Record<string, unknown>), ...patch } }
            : n,
        ),
      );
    },
    [setNodes, nodeId],
  );
}

/** 类型化的 update 工厂 — 节点组件可直接 import 使用 */
export function useUpdateNodeDataTyped<T extends Record<string, unknown>>(nodeId: string) {
  const update = useUpdateNodeData(nodeId);
  return useMemo(
    () => (patch: Partial<T>) => update(patch as NodeDataPatch),
    [update],
  );
}
