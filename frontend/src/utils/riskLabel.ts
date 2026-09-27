import type { RiskLevel } from "@/domain/types";

export function isAhead(predictedDelaySeconds: number | null): boolean {
  return predictedDelaySeconds !== null && predictedDelaySeconds < 0;
}

export function riskPhrase(risk: RiskLevel, predictedDelaySeconds: number | null): string {
  const ahead = isAhead(predictedDelaySeconds);
  if (risk === "high") return ahead ? "риск опережения" : "риск опоздания";
  if (risk === "medium") return ahead ? "небольшое опережение" : "небольшое отставание";
  return "по графику";
}

export function incidentTitle(risk: "medium" | "high", predictedDelaySeconds: number | null): string {
  const ahead = isAhead(predictedDelaySeconds);
  const level = risk === "high" ? "высокий" : "средний";
  return `Инцидент: ${level} риск ${ahead ? "опережения" : "опоздания"}`;
}
