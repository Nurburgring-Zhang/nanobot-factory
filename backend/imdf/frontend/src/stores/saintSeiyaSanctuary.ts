/**
 * R3.5-W2 stub: 圣斗士十二宫 store
 */
import { create } from 'zustand';

interface SaintSeiyaState {
  hadesUnlockedAt: number | null;
  hadesModeActive: boolean;
  setHadesModeActive: (active: boolean) => void;
}

export const useSaintSeiyaSanctuaryStore = create<SaintSeiyaState>((set) => ({
  hadesUnlockedAt: null,
  hadesModeActive: false,
  setHadesModeActive: (active) => set({ hadesModeActive: active }),
}));

export function seedSaintSeiyaGoldClothsForHadesTest(): void {
  useSaintSeiyaSanctuaryStore.setState({ hadesUnlockedAt: Date.now() });
}
