import { RiskLevel } from "@/domain/types";
import { getBusVariant, BusVariant } from "@/utils/busVariant";

const RISK_COLOR: Record<string, string> = {
  low: "#30d158",
  medium: "#ffd60a",
  high: "#ff453a",
  unknown: "#8e8e93"
};

interface Props {
  risk: RiskLevel;
  /** Pass either an explicit variant, or a vehicleId to derive it deterministically. */
  variant?: BusVariant;
  vehicleId?: string;
  /** Rendered width in px (height follows each variant's own aspect ratio). */
  size?: number;
}

/**
 * The two top-down bus icons live here, and only here. BusMap renders this
 * exact component (via renderToStaticMarkup) to build its map icon images —
 * it does not define its own bus geometry anywhere.
 *
 *  - "v1" minibus: short, chunky body with a window band and a small roof
 *    vent. Visually distinct from v2 — not just a scaled-down version of it.
 *  - "v2" electrobus: long, low-floor city bus. No windshield; an elongated
 *    roof-equipment strip and a thin full-width rear light on the back edge.
 */
export function BusTopIcon({ risk, variant, vehicleId, size = 40 }: Props) {
  const color = RISK_COLOR[risk];
  const dark = adjustColor(color, -40);
  const resolvedVariant: BusVariant =
    variant ?? (vehicleId ? getBusVariant(vehicleId) : "v1");

  return resolvedVariant === "v2" ? (
    <svg
      width={size}
      height={size * (44 / 30)}
      viewBox="0 0 30 68"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* ==================== BODY ==================== */}
      <path
        d="
          M 8 2
          C 4.5 2 2.5 4.8 2.5 8
          L 2.5 59
          C 2.5 63.5 5 66 8.5 66
          L 21.5 66
          C 25 66 27.5 63.5 27.5 59
          L 27.5 8
          C 27.5 4.8 25.5 2 22 2
          Z
        "
        fill={color}
      />

      {/* ==================== FRONT ==================== */}

      {/* Windshield */}
      <path
        d="
          M 5.2 8.8
          C 5.8 6.3 7.2 5.1 9.8 5
          L 20.2 5
          C 22.8 5.1 24.2 6.3 24.8 8.8
          L 23.8 16.2
          C 23.5 17.7 22.5 18.5 21 18.5
          L 9 18.5
          C 7.5 18.5 6.5 17.7 6.2 16.2
          Z
        "
        fill="#344b60"
      />

      {/* Windshield subtle reflection */}
      <path
        d="
          M 14.5 5.2
          L 18 5.2
          L 12 17.8
          L 9.5 17.8
          Z
        "
        fill="#6f8799"
        opacity="0.45"
      />

      <path
        d="
          M 19 5.2
          L 21 5.4
          L 16 17.8
          L 13.5 17.8
          Z
        "
        fill="#6f8799"
        opacity="0.3"
      />

      {/* ==================== SIDE WINDOWS ==================== */}

      {/* Left window strip */}
      <path
        d="
          M 3.5 21
          L 6.5 21
          L 6.5 58
          C 5.5 57.8 4.5 56.5 4.5 54.5
          Z
        "
        fill="#344b60"
      />

      {/* Right window strip */}
      <path
        d="
          M 23.5 21
          L 26.5 21
          L 26.5 54.5
          C 26.5 56.5 25.5 57.8 23.5 58
          Z
        "
        fill="#344b60"
      />

      {/* ==================== ROOF ==================== */}

      {/* Central roof equipment */}
      {/*<rect*/}
      {/*  x="11.2"*/}
      {/*  y="23"*/}
      {/*  width="7.6"*/}
      {/*  height="11"*/}
      {/*  rx="2"*/}
      {/*  fill={dark}*/}
      {/*/>*/}

      {/* Roof ridges */}
      <path
        d="M 9.5 22 L 9.5 58"
        stroke={dark}
        strokeWidth="0.8"
        opacity="0.35"
      />

      <path
        d="M 20.5 22 L 20.5 58"
        stroke={dark}
        strokeWidth="0.8"
        opacity="0.35"
      />

      {/* ==================== MIRRORS ==================== */}

      <rect
        x="0.5"
        y="17.5"
        width="3.2"
        height="5.2"
        rx="1.4"
        fill={dark}
      />

      <rect
        x="26.3"
        y="17.5"
        width="3.2"
        height="5.2"
        rx="1.4"
        fill={dark}
      />

      {/* ==================== HEADLIGHTS ==================== */}

      <path
        d="
          M 3.1 3.9
          C 4 3 5.2 2.5 7 2.4
          L 6 5.7
          L 3 7
          Z
        "
        fill="#e8edf0"
      />

      <path
        d="
          M 23 2.4
          C 24.8 2.5 26 3 26.9 3.9
          L 27 7
          L 24 5.7
          Z
        "
        fill="#e8edf0"
      />

      {/* ==================== REAR ==================== */}

      {/* Rear bumper / subtle lower panel */}
      <path
        d="
          M 5 62
          C 6 64.2 7.5 65 10 65
          L 20 65
          C 22.5 65 24 64.2 25 62
          L 25.5 64
          C 24.5 65.4 23 66 21 66
          L 9 66
          C 7 66 5.5 65.4 4.5 64
          Z
        "
        fill={dark}
        opacity="0.45"
      />

      {/* Thin rear light — at the bottom edge */}
      <rect
        x="8"
        y="66"
        width="14"
        height="1"
        rx="0.5"
        fill="#ff453a"
      />
    </svg>
  ) : (
    <svg
      width={size}
      height={size * (68 / 30)}
      viewBox="0 0 30 68"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Body */}
      <rect x="2" y="2" width="26" height="64" rx="3" fill={color} />

      {/* ==================== FRONT ==================== */}

      {/* Front windshield - covers rounded corners */}
      <path
        d="
          M 2 4
          L 2 8.5
          C 2 4.5 4.5 2 8.5 2
          L 21.5 2
          C 25.5 2 28 4.5 28 8.5
          L 28 4
          Z
        "
        fill="#344b60"
      />

      {/* ==================== SIDE WINDOWS ==================== */}

      {/* Left window strip */}
      <rect x="2" y="15" width="2.5" height="45" rx="0.5" fill="#344b60" />

      {/* Right window strip */}
      <rect x="25.5" y="15" width="2.5" height="45" rx="0.5" fill="#344b60" />

      {/* ==================== ROOF ==================== */}

      {/* Elongated roof-equipment strip */}
      <rect x="8.5" y="35" width="13" height="17" rx="3" fill={dark} />

      {/* ==================== REAR ==================== */}

      {/* Rear light */}
      <rect x="5" y="65" width="20" height="1" rx="1" fill="#ff453a" /> </svg>
  );
}

// Helper to darken color
function adjustColor(color: string, amount: number): string {
  const hex = color.replace('#', '');
  const num = parseInt(hex, 16);
  const r = Math.min(255, Math.max(0, (num >> 16) + amount));
  const g = Math.min(255, Math.max(0, ((num >> 8) & 0x00FF) + amount));
  const b = Math.min(255, Math.max(0, (num & 0x0000FF) + amount));
  return `#${(1 << 24 | r << 16 | g << 8 | b).toString(16).slice(1)}`;
}