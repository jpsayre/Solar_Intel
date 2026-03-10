/**
 * Convert public.homes.index (e.g. BOULDER_CO_1014) to the storage object path.
 * Files are stored as BOULDER_CO_1014.png (matching the index directly).
 */
export function indexToImagePath(index: string): string {
  return `${index}.png`;
}
