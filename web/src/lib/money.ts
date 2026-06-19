// Canonical USD / list-price formatters for the Olune UI.
//
// Every surface that renders a dollar amount or per-million list price imports
// from here — no local copies, no inline `$${n.toFixed(...)}`. Three cost
// grammars are intentional: summary (byline/meter), precise (breakdown/
// estimate), and meter (usage bar).

/** Per-turn / run-cost byline grammar: sub-cent floor + 4·3·2 decimals. */
export function formatUsdSummary(amount: number): string {
  if (amount === 0) return "$0.00";
  if (amount < 0.0001) return "<$0.0001";
  const decimals = amount < 0.01 ? 4 : amount < 1 ? 3 : 2;
  return `$${amount.toFixed(decimals)}`;
}

/** Breakdown / pre-send estimate: finer decimals for sub-cent lines (6·4·2). */
export function formatUsdPrecise(amount: number): string {
  if (amount === 0) return "$0.00";
  const decimals = amount < 0.01 ? 6 : amount < 1 ? 4 : 2;
  return `$${amount.toFixed(decimals)}`;
}

/** Usage-meter spend remaining: 4 decimals below $1, else 2. */
export function formatUsdMeter(amount: number): string {
  return `$${amount.toFixed(amount < 1 ? 4 : 2)}`;
}

/** Spend analytics + settings ledger rows (Intl currency, up to 6 frac). */
export function formatUsdCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(amount);
}

/** Settings fields where a cap/balance may be unset. */
export function formatUsdCurrencyOrNa(
  value: number | null | undefined,
): string {
  if (value === null || value === undefined) return "n/a";
  return formatUsdCurrency(value);
}

/** Registry list price in cost-breakdown popover ($x/M with locale grouping). */
export function formatPricePerM(perM: number): string {
  return `$${perM.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })}/M`;
}

/** Model-picker tier row hint: "$0.14/M in · $0.28/M out". Empty when unpriced. */
export function formatTierListPriceLine(
  listPriceInPerM: number,
  listPriceOutPerM: number,
): string {
  if (listPriceInPerM <= 0 && listPriceOutPerM <= 0) return "";
  return `$${listPriceInPerM}/M in · $${listPriceOutPerM}/M out`;
}

/** Model directory per-million line; "varies" for auto / unpriced routes. */
export function formatDirectoryPricePerM(perM: number): string {
  if (!Number.isFinite(perM) || perM <= 0) return "varies";
  return `$${perM.toFixed(2)}/M`;
}

/** Compact cost badge in search results (fixed 4 decimal places). */
export function formatUsdSearchBadge(costUsd: number): string {
  return `$${costUsd.toFixed(4)}`;
}
