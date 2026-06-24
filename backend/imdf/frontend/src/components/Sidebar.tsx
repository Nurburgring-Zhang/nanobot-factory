/**
 * R3.5-W2 stub: Sidebar
 */
import type { FC } from 'react';
import type { NodeType } from '../types/canvas';

interface SidebarProps {
  onAddNode?: (type: NodeType) => void;
}

const Sidebar: FC<SidebarProps> = () => {
  return <aside className="t8-sidebar" data-stub="Sidebar" />;
};

export default Sidebar;
