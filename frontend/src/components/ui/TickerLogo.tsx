"use client";
import { useState, useMemo } from "react";

interface Props {
  ticker: string;
  size?: number;   // px, default 24
  rounded?: "full" | "md" | "lg";
}

export default function TickerLogo({ ticker, size = 24, rounded = "full" }: Props) {
  const [srcIdx, setSrcIdx] = useState(0);

  const color = useMemo(() => {
    const hue = ticker.split("").reduce((n, c) => n + c.charCodeAt(0), 0) % 360;
    return `hsl(${hue},55%,38%)`;
  }, [ticker]);

  const sources = useMemo(() => [
    `https://financialmodelingprep.com/image-stock/${ticker.toUpperCase()}.png`,
    `https://assets.parqet.com/logos/symbol/${ticker.toUpperCase()}?format=png`,
  ], [ticker]);

  const fontSize = Math.max(8, Math.round(size * 0.38));
  const cls = `rounded-${rounded}`;

  if (srcIdx >= sources.length) {
    return (
      <div
        className={`${cls} flex items-center justify-center font-bold text-white shrink-0`}
        style={{ width: size, height: size, backgroundColor: color, fontSize }}
      >
        {ticker.slice(0, 2).toUpperCase()}
      </div>
    );
  }

  return (
    <img
      src={sources[srcIdx]}
      alt={ticker}
      width={size}
      height={size}
      className={`${cls} object-contain bg-zinc-800 shrink-0`}
      onError={() => setSrcIdx(i => i + 1)}
    />
  );
}
