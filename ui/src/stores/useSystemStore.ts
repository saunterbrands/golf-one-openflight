import { create } from 'zustand';

interface SystemState {
  connected: boolean;
  mockMode: boolean;
  debugMode: boolean;
  setConnected: (connected: boolean) => void;
  setMockMode: (mockMode: boolean) => void;
  setDebugMode: (debugMode: boolean) => void;
}

export const useSystemStore = create<SystemState>((set) => ({
  connected: false,
  mockMode: false,
  debugMode: false,
  setConnected: (connected) => set({ connected }),
  setMockMode: (mockMode) => set({ mockMode }),
  setDebugMode: (debugMode) => set({ debugMode }),
}));
