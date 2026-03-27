/**
 * TradingView symbol mapping helpers.
 *
 * TradingView uses "EXCHANGE:TICKER" format (e.g. "NASDAQ:MSFT").
 * yfinance returns exchange codes like "NMS", "NYQ" that must be normalised.
 */

const TV_EXCHANGE: Record<string, string> = {
  // NASDAQ variants
  NASDAQ: "NASDAQ",
  NMS:    "NASDAQ",  // NASDAQ Global Select Market
  NGM:    "NASDAQ",  // NASDAQ Global Market
  NCM:    "NASDAQ",  // NASDAQ Capital Market
  // NYSE variants
  NYSE:   "NYSE",
  NYQ:    "NYSE",
  // AMEX variants
  AMEX:   "AMEX",
  ASE:    "AMEX",
  PCX:    "AMEX",
  // OTC variants
  OTC:    "OTC",
  OTCMKTS:"OTC",
  PNK:    "OTC",
  // International
  TSX:    "TSX",
  LSE:    "LSE",
  ASX:    "ASX",
  NSE:    "NSE",
  XETRA:  "XETR",
  HKG:    "HKEX",
};

/**
 * Map a ticker + yfinance exchange code to a TradingView symbol string.
 * Falls back to bare ticker if exchange is unknown.
 */
export function mapToTvSymbol(ticker: string, exchange?: string | null): string {
  const sym = ticker.toUpperCase().trim();
  const tvEx = TV_EXCHANGE[(exchange ?? "").toUpperCase().trim()];
  return tvEx ? `${tvEx}:${sym}` : sym;
}

export interface TvWidgetConfig {
  symbol: string;
  container_id: string;
  autosize: boolean;
  theme: "dark" | "light";
  style: string;
  locale: string;
  toolbar_bg: string;
  enable_publishing: boolean;
  allow_symbol_change: boolean;
  save_image: boolean;
  hide_side_toolbar: boolean;
  range: string;
}

export function buildTvConfig(symbol: string, containerId: string): TvWidgetConfig {
  return {
    symbol,
    container_id:       containerId,
    autosize:           true,
    theme:              "dark",
    style:              "1",
    locale:             "en",
    toolbar_bg:         "#18181b",
    enable_publishing:  false,
    allow_symbol_change: false,
    save_image:         false,
    hide_side_toolbar:  false,
    range:              "12M",
  };
}
