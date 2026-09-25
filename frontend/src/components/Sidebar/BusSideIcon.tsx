import { RiskLevel } from "@/domain/types";

const RISK_COLOR: Record<RiskLevel, string> = {
  low: "#30d158",
  mid: "#ffd60a",
  high: "#ff453a"
};

interface Props {
  risk: RiskLevel;
  number: string;
}

/**
 * Minimalist side-view bus silhouette with the route/garage number
 * printed directly on the body, per the sidebar card spec.
 */
export function BusSideIcon({ risk, number }: Props) {
  const color = RISK_COLOR[risk];
  return (
    <svg width="52" height="30" viewBox="0 0 52 30" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="6" width="46" height="16" rx="5" fill={color} />
      <rect x="6" y="9" width="8" height="6" rx="1.5" fill="#0a0a0c" fillOpacity="0.35" />
      <circle cx="13" cy="24" r="3.2" fill="#1c1c21" stroke="#0a0a0c" strokeWidth="0.5" />
      <circle cx="38" cy="24" r="3.2" fill="#1c1c21" stroke="#0a0a0c" strokeWidth="0.5" />
      <text
        x="31"
        y="17"
        textAnchor="middle"
        fontSize="9"
        fontWeight="700"
        fill="#0a0a0c"
        fontFamily="-apple-system, sans-serif"
      >
        {number}
      </text>
    </svg>
  );
}
