// Canonical USD / list-price formatters for the Olune UI.
//
// Every surface that renders a dollar amount imports from here — no local
// copies, no inline `$${n.toFixed(...)}`. Two cost grammars are intentional:
// summary (byline/meter) and meter (usage bar).

/** Per-turn / run-cost byline grammar: sub-cent floor + 4·3·2 decimals. */
export function formatUsdSummary(amount: number): string {
  if (amount === 0) return "$0.00";
  if (amount < 0.0001) return "<$0.0001";
  const decimals = amount < 0.01 ? 4 : amount < 1 ? 3 : 2;
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
