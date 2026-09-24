import { useEffect, useRef } from 'react';

/** Call `fn` every `interval` ms while `active`; pauses when the tab is hidden. */
export function usePolling(fn, active, interval = 5000) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!active) return undefined;
    let timer;
    const tick = async () => {
      if (!document.hidden) await fnRef.current();
      timer = setTimeout(tick, interval);
    };
    timer = setTimeout(tick, interval);
    return () => clearTimeout(timer);
  }, [active, interval]);
}
