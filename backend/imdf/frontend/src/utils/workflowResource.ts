/**
 * R3.5-W2 stub: 工作流 manifest → 画布 fragment
 */

export interface WorkflowManifest {
  nodes?: unknown[];
  edges?: unknown[];
  [key: string]: unknown;
}

export interface WorkflowFragment {
  nodes: unknown[];
  edges: unknown[];
  manifest: WorkflowManifest;
}

export function workflowManifestToFragment(
  manifest: WorkflowManifest
): WorkflowFragment {
  return {
    nodes: Array.isArray(manifest.nodes) ? manifest.nodes : [],
    edges: Array.isArray(manifest.edges) ? manifest.edges : [],
    manifest,
  };
}
