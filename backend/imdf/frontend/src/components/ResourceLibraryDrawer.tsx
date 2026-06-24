/**
 * R3.5-W2 stub: 资源库抽屉 (懒加载组件)
 */
import type { FC } from 'react';
import type { ResourceItem } from '../services/api';

interface ResourceLibraryDrawerProps {
  open: boolean;
  onClose: () => void;
  onInsertMaterial?: (item: ResourceItem) => void | Promise<void>;
}

const ResourceLibraryDrawer: FC<ResourceLibraryDrawerProps> = () => null;

export default ResourceLibraryDrawer;
