export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api" + path, {
    ...init,
    headers: {
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let message = "The request failed. Please try again.";
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail
                .map(
                  (e: { loc: string[]; msg: string }) =>
                    `${e.loc.slice(1).join(".")}: ${e.msg}`,
                )
                .join("; ")
            : message;
    } catch {}
    throw new Error(message);
  }
  return response.json();
}
export const money = (
  value: string | number | null | undefined,
  compact = false,
) =>
  value === null || value === undefined
    ? "Insufficient data"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: compact ? 1 : 0,
        notation: compact ? "compact" : "standard",
      }).format(Number(value));
export const number = (value: string | null | undefined, suffix = "") =>
  value === null || value === undefined
    ? "Insufficient data"
    : Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 }) +
      suffix;
