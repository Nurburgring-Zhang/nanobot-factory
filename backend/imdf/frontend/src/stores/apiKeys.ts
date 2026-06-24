/**
 * R3.5-W2 stub: API Key store
 */
import { create } from 'zustand';

interface ApiKeysState {
  load: () => Promise<void> | void;
}

export const useApiKeysStore = create<ApiKeysState>(() => ({
  load: () => undefined,
}));
