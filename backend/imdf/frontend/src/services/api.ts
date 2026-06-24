/**
 * R3.5-W2 stub: 后端 API 服务
 *
 * 真实接口由 R2 / R3 后端 worker 负责；本 stub 只保证 imdf-app.tsx 使用的
 * `checkBackendStatus()` 与 `updateResourceItem()` 存在并返回合理类型。
 */

export type ResourceKind =
  | 'image'
  | 'video'
  | 'audio'
  | 'pose'
  | 'workflow'
  | 'set'
  | 'panorama'
  | string;

export type MaterialSetKind = 'character' | 'scene' | 'prop' | (string & {});

export interface MaterialSetItem {
  id?: string;
  url?: string;
  name?: string;
  [key: string]: unknown;
}

export interface ResourceItem {
  id: string;
  kind: ResourceKind;
  title?: string;
  originalName?: string;
  fileUrl?: string;
  size?: number;
  mime?: string;
  materialSetKind?: MaterialSetKind;
  materialSetItems?: MaterialSetItem[];
  [key: string]: unknown;
}

export async function checkBackendStatus(): Promise<boolean> {
  return true;
}

export async function updateResourceItem(
  id: string,
  patch: { touch?: boolean; [key: string]: unknown }
): Promise<ResourceItem | null> {
  void id;
  void patch;
  return null;
}

const api = {
  checkBackendStatus,
  updateResourceItem,
};

export default api;
