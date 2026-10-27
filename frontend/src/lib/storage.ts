import type { Identity } from "./types";

/**
 * Tożsamość w localStorage — to ona sprawia, że zablokowanie ekranu telefonu
 * albo odświeżenie strony nie tworzy nowego uczestnika.
 *
 * Host i gość mają osobne klucze, bo obie role potrafią mieszkać w jednej
 * przeglądarce: na laptopie otwierasz ekran hosta, a obok testujesz widok gościa.
 */
const KEYS = {
  host: "spotkanio.host",
  guest: "spotkanio.guest",
} as const;

export type Slot = keyof typeof KEYS;

export function loadIdentity(slot: Slot): Identity | null {
  try {
    const raw = localStorage.getItem(KEYS[slot]);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Identity;
    return parsed.token && parsed.code ? parsed : null;
  } catch {
    return null;
  }
}

export function saveIdentity(slot: Slot, identity: Identity): void {
  localStorage.setItem(KEYS[slot], JSON.stringify(identity));
}

export function clearIdentity(slot: Slot): void {
  localStorage.removeItem(KEYS[slot]);
}
