/**
 * R3.5-W2 stub: Canvas 主组件
 *
 * 类型签名（AddNodeFn / InsertWorkflowFn）由 imdf-app.tsx 行 10-11 引用。
 * 真实画布实现由 R3-W5/R3-W6 worker 负责，本 stub 只保证类型与渲染可用。
 */
import type { FC, MutableRefObject } from 'react';
import type { NodeType } from '../types/canvas';

export type AddNodeFn = (
  type: NodeType,
  options?: { data?: Record<string, unknown> }
) => void;

export type InsertWorkflowFn = (
  fragment: unknown,
  options?: { title?: string }
) => void;

export interface CanvasProps {
  onAddNodeRef?: MutableRefObject<AddNodeFn | null>;
  onInsertWorkflowRef?: MutableRefObject<InsertWorkflowFn | null>;
}

const Canvas: FC<CanvasProps> = () => {
  return <div className="t8-canvas" data-stub="Canvas" />;
};

export default Canvas;
