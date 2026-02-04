/**
 * Convert public.homes.index (e.g. BOULDER_CO_1014) to the storage object path.
 * Files are saved by download_map_images as {location}_{id}.png (e.g. Boulder_CO_1014.png),
 * so we title-case the first segment to match.
 */
export function indexToImagePath(index: string): string {
  const parts = index.split("_");
  if (parts.length === 0) return `${index}.png`;
  const first = parts[0];
  const titleCased = first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
  const rest = parts.slice(1).join("_");
  return rest ? `${titleCased}_${rest}.png` : `${titleCased}.png`;
}
