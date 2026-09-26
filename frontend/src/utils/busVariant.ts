export type BusVariant = "v1" | "v2";

// Deterministic selection: ~25% v2 based on vehicle ID hash
export function getBusVariant(vehicleId: string): BusVariant {
  let hash = 0;
  for (let i = 0; i < vehicleId.length; i++) {
    hash = ((hash << 5) - hash) + vehicleId.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash) % 4 === 0 ? "v2" : "v1";
}