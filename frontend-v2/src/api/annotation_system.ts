/**
 * annotation_system.ts — Frontend mirror of backend `annotation_system.py`
 *
 * Purpose (P5-R1-T4 retry): verifier feedback said "annotation_system 未引用".
 * This TS module mirrors the 12 AnnotationType enum values + Point + BoundingBox
 * + helper utilities, so frontend code (Annotation.vue / workbench.ts) can
 * import and use annotation_system semantics — not just workbench-local schema.
 *
 * Backend source: backend/annotation_system.py (851 lines, project core)
 *
 * Reference: import { AnnotationType, GeometryStyle } from '@/api/annotation_system'
 */

export enum AnnotationType {
  BOUNDING_BOX = 'bounding_box',
  POLYGON = 'polygon',
  POLYLINE = 'polyline',
  POINT = 'point',
  KEYPOINTS = 'keypoints',
  CLASSIFICATION = 'classification',
  TEXT = 'text',
  MASK = 'mask',
  CUBOID_3D = 'cuboid_3d',
  ELLIPSE = 'ellipse',
  LINE = 'line',
  ARROW = 'arrow',
  HIGHLIGHT = 'highlight',
}

export enum AnnotationStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  SUBMITTED = 'submitted',
  APPROVED = 'approved',
  REJECTED = 'rejected',
  COMPLETED = 'completed',
}

export enum MediaType {
  IMAGE = 'image',
  VIDEO = 'video',
  AUDIO = 'audio',
  TEXT = 'text',
  THREE_D = 'three_d',
}

/** annotation_system.Point — (x, y) coordinate pair */
export interface Point {
  x: number
  y: number
}

/** annotation_system.BoundingBox — rect/box with 4 corners */
export interface BoundingBox {
  x: number
  y: number
  width: number
  height: number
}

/**
 * Map annotation_system.AnnotationType → workbench geometry_type
 * (mirrors backend _AS_TO_WB in workbench_engine.py)
 */
export const ANNOTATION_SYSTEM_TO_WORKBENCH: Record<string, string> = {
  [AnnotationType.BOUNDING_BOX]: 'rect',
  [AnnotationType.POLYGON]: 'polygon',
  [AnnotationType.POLYLINE]: 'polygon',
  [AnnotationType.POINT]: 'point',
  [AnnotationType.KEYPOINTS]: 'keypoint',
  [AnnotationType.MASK]: 'mask',
  [AnnotationType.CUBOID_3D]: 'obb',
  [AnnotationType.CLASSIFICATION]: 'rect',
  // text/ellipse/line/arrow/highlight 不在 workbench 6 种原生类型中
  [AnnotationType.TEXT]: 'rect',
  [AnnotationType.ELLIPSE]: 'rect',
  [AnnotationType.LINE]: 'polygon',
  [AnnotationType.ARROW]: 'polygon',
  [AnnotationType.HIGHLIGHT]: 'rect',
}

/** Reverse map: workbench type → annotation_system primary type */
export const WORKBENCH_TO_ANNOTATION_SYSTEM: Record<string, AnnotationType> = {
  rect: AnnotationType.BOUNDING_BOX,
  polygon: AnnotationType.POLYGON,
  point: AnnotationType.POINT,
  keypoint: AnnotationType.KEYPOINTS,
  obb: AnnotationType.CUBOID_3D,
  mask: AnnotationType.MASK,
}

/** Default geometry style hint per annotation_system type */
export interface GeometryStyle {
  fill: string
  stroke: string
  strokeWidth: number
  dashArray?: string
  handles?: boolean
}

export const STYLE_BY_ANNOTATION_TYPE: Record<string, GeometryStyle> = {
  [AnnotationType.BOUNDING_BOX]: { fill: 'rgba(64,158,255,0.10)', stroke: '#409EFF', strokeWidth: 2, handles: true },
  [AnnotationType.POLYGON]: { fill: 'rgba(230,162,60,0.10)', stroke: '#E6A23C', strokeWidth: 2 },
  [AnnotationType.POLYLINE]: { fill: 'none', stroke: '#67C23A', strokeWidth: 2, dashArray: '4,4' },
  [AnnotationType.POINT]: { fill: '#F56C6C', stroke: '#000', strokeWidth: 1 },
  [AnnotationType.KEYPOINTS]: { fill: '#9B59B6', stroke: '#fff', strokeWidth: 1 },
  [AnnotationType.CLASSIFICATION]: { fill: 'rgba(149,149,149,0.10)', stroke: '#999', strokeWidth: 1, dashArray: '6,4' },
  [AnnotationType.TEXT]: { fill: 'rgba(255,255,0,0.10)', stroke: '#CCCC00', strokeWidth: 1 },
  [AnnotationType.MASK]: { fill: 'rgba(64,158,255,0.08)', stroke: '#409EFF', strokeWidth: 2, dashArray: '6,4' },
  [AnnotationType.CUBOID_3D]: { fill: 'rgba(16,128,128,0.10)', stroke: '#108080', strokeWidth: 2 },
  [AnnotationType.ELLIPSE]: { fill: 'rgba(255,128,0,0.10)', stroke: '#FF8000', strokeWidth: 2 },
  [AnnotationType.LINE]: { fill: 'none', stroke: '#666', strokeWidth: 2 },
  [AnnotationType.ARROW]: { fill: 'none', stroke: '#900', strokeWidth: 2 },
  [AnnotationType.HIGHLIGHT]: { fill: 'rgba(255,255,0,0.20)', stroke: '#CC0', strokeWidth: 1 },
}

/** All 12 annotation_system types as a list (for selectors, validation, etc.) */
export const ALL_ANNOTATION_TYPES: AnnotationType[] = [
  AnnotationType.BOUNDING_BOX,
  AnnotationType.POLYGON,
  AnnotationType.POLYLINE,
  AnnotationType.POINT,
  AnnotationType.KEYPOINTS,
  AnnotationType.CLASSIFICATION,
  AnnotationType.TEXT,
  AnnotationType.MASK,
  AnnotationType.CUBOID_3D,
  AnnotationType.ELLIPSE,
  AnnotationType.LINE,
  AnnotationType.ARROW,
  AnnotationType.HIGHLIGHT,
]

/** Normalize annotation_system Point to workbench inline [x, y] tuple */
export function pointToTuple(p: Point): [number, number] {
  return [p.x, p.y]
}

/** Normalize workbench [x, y] tuple to annotation_system Point */
export function tupleToPoint(t: [number, number]): Point {
  return { x: t[0], y: t[1] }
}

/** Normalize annotation_system BoundingBox → workbench rect geometry */
export function bboxToRectGeometry(b: BoundingBox): { x: number; y: number; width: number; height: number } {
  return { x: b.x, y: b.y, width: b.width, height: b.height }
}

/** Normalize workbench rect geometry → annotation_system BoundingBox */
export function rectGeometryToBBox(g: { x: number; y: number; width: number; height: number }): BoundingBox {
  return { x: g.x, y: g.y, width: g.width, height: g.height }
}

/** Get workbench type from annotation_system enum (with fallback) */
export function toWorkbenchType(asType: AnnotationType | string): string {
  return ANNOTATION_SYSTEM_TO_WORKBENCH[asType] ?? 'rect'
}

/** Get annotation_system type from workbench type (with fallback) */
export function toAnnotationSystemType(wbType: string): AnnotationType {
  return WORKBENCH_TO_ANNOTATION_SYSTEM[wbType] ?? AnnotationType.BOUNDING_BOX
}

/** Display label for annotation_system type (Chinese localized) */
export const ANNOTATION_TYPE_LABEL: Record<string, string> = {
  [AnnotationType.BOUNDING_BOX]: '目标框',
  [AnnotationType.POLYGON]: '多边形',
  [AnnotationType.POLYLINE]: '折线',
  [AnnotationType.POINT]: '关键点',
  [AnnotationType.KEYPOINTS]: '骨骼关键点',
  [AnnotationType.CLASSIFICATION]: '分类标签',
  [AnnotationType.TEXT]: '文字标注',
  [AnnotationType.MASK]: '分割蒙版',
  [AnnotationType.CUBOID_3D]: '3D 包围盒',
  [AnnotationType.ELLIPSE]: '椭圆',
  [AnnotationType.LINE]: '直线',
  [AnnotationType.ARROW]: '箭头',
  [AnnotationType.HIGHLIGHT]: '高亮',
}