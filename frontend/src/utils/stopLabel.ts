export function stopLabel(stop: { sequence: number; address?: string | null }): string {
  return stop.address?.trim() || `№${stop.sequence}`;
}
