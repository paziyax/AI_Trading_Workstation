"use client";

import { useEffect, useRef, useState } from "react";

export type FlashState = "up" | "down" | "none";

/**
 * Flash for 500 ms on a genuine price change. A repeated frame carrying the
 * same price must not restart the animation, otherwise a quiet market would
 * strobe forever.
 */
export function usePriceFlash(price: number | null | undefined, duration = 500): FlashState {
  const [flash, setFlash] = useState<FlashState>("none");
  const previous = useRef<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof price !== "number" || !Number.isFinite(price)) return;

    const prior = previous.current;
    previous.current = price;
    if (prior === null || price === prior) return;

    setFlash(price > prior ? "up" : "down");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setFlash("none");
      timer.current = null;
    }, duration);
  }, [price, duration]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return flash;
}
