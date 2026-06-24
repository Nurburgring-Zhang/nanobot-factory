/**
 * R3.5-W2 stub: 画布节点类型
 *
 * 真实节点枚举由 R3-W4/R3-W5 worker 在 nodes/ 目录下补充。
 * 此处列出 imdf-app.tsx 中实际使用过的节点类型。
 */

export type NodeType =
  | 'portrait-master'
  | 'pose-master'
  | 'material-set'
  | 'upload'
  | (string & {});
