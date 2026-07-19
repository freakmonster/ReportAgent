'use client';

import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface UIState {
  darkMode: boolean;
  toggleDarkMode: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  darkMode: false,
  toggleDarkMode: () => set((s) => ({ darkMode: !s.darkMode })),
}));
