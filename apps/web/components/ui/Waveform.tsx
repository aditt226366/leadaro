"use client";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

/**
 * Speaking indicator for the live console.
 *
 * Deliberately NOT a real audio analysis — the browser never receives the call
 * audio, so any "waveform" here would be theatre either way. This animates only
 * while a call is genuinely active and freezes flat when it isn't, so it
 * carries one honest bit of information rather than implying a signal we don't
 * have.
 */
export function Waveform({
  active,
  bars = 32,
  className,
}: {
  active: boolean;
  bars?: number;
  className?: string;
}) {
  const [tick, setTick] = useState(0);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (!active) return;
    let last = 0;
    const loop = (t: number) => {
      // ~12fps is enough to read as "live" and costs almost nothing.
      if (t - last > 80) {
        setTick((n) => n + 1);
        last = t;
      }
      raf.current = requestAnimationFrame(loop);
    };
    raf.current = requestAnimationFrame(loop);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [active]);

  return (
    <div
      className={cn("flex h-8 items-center gap-[2px]", className)}
      aria-hidden
    >
      {Array.from({ length: bars }).map((_, i) => {
        const h = active
          ? 22 + Math.abs(Math.sin((i + tick) * 0.55)) * 68
          : 12;
        return (
          <span
            key={i}
            className={cn(
              "w-[3px] rounded-full transition-all duration-100",
              active ? "bg-primary" : "bg-line-strong",
            )}
            style={{ height: `${h}%` }}
          />
        );
      })}
    </div>
  );
}

/** Small pulsing dot for "connected / live" status. */
export function LiveDot({ on }: { on: boolean }) {
  return (
    <span className="relative flex size-2">
      {on && (
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-pos opacity-70" />
      )}
      <span
        className={cn(
          "relative inline-flex size-2 rounded-full",
          on ? "bg-pos" : "bg-faint",
        )}
      />
    </span>
  );
}
