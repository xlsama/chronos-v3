import { create } from "zustand";

interface CreateIncidentDialogState {
  open: boolean;
  setOpen: (open: boolean) => void;
}

export const useCreateIncidentDialogStore = create<CreateIncidentDialogState>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
}));
