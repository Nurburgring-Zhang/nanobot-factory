/**
 * R3.5-W2 stub: 七龙珠雷达 store
 */
import { create } from 'zustand';

interface DragonBallRadarState {
  shenronUnlockedAt: number | null;
  shenronModeActive: boolean;
  setShenronModeActive: (active: boolean) => void;
}

export const useDragonBallRadarStore = create<DragonBallRadarState>((set) => ({
  shenronUnlockedAt: null,
  shenronModeActive: false,
  setShenronModeActive: (active) => set({ shenronModeActive: active }),
}));

export function seedDragonBallRadarForShenronTest(count: number): void {
  useDragonBallRadarStore.setState({ shenronUnlockedAt: Date.now() });
  void count;
}
