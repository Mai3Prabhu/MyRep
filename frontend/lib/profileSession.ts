const STORAGE_KEY = "myrep.profileId";

export function getSavedProfileId(): string | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(STORAGE_KEY);
  return value && value.trim() ? value.trim() : null;
}

export function saveProfileId(profileId: string): void {
  window.localStorage.setItem(STORAGE_KEY, profileId);
}
