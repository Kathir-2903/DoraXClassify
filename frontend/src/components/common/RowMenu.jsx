import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { MoreHorizontal } from 'lucide-react';

/**
 * A "..." row-action menu. The popup is rendered into a portal (like Modal)
 * instead of positioned inline, because inline rows sit inside a table with
 * `overflow-x: auto` and a `position: sticky` action column — an in-flow
 * absolute popup there gets visually painted underneath the sticky cells of
 * later rows (same stacking level, later in DOM order wins), and can get
 * clipped by the scroll container. Fixed-positioning from the button's own
 * screen coordinates sidesteps both problems.
 */
export function RowMenu({ items, label = 'Actions' }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);
  const visibleItems = items.filter(Boolean);

  const updateCoords = () => {
    const rect = btnRef.current?.getBoundingClientRect();
    if (!rect) return;
    const estimatedHeight = visibleItems.length * 34 + 10;
    const spaceBelow = window.innerHeight - rect.bottom;
    const flipUp = spaceBelow < estimatedHeight && rect.top > estimatedHeight;
    setCoords({
      right: Math.max(8, window.innerWidth - rect.right),
      ...(flipUp ? { bottom: window.innerHeight - rect.top + 6 } : { top: rect.bottom + 6 }),
    });
  };

  useLayoutEffect(() => {
    if (!open) return undefined;
    updateCoords();
    // capture: true so scrolling inside the table's own overflow-x wrapper (not just the window) repositions the menu too.
    window.addEventListener('scroll', updateCoords, true);
    window.addEventListener('resize', updateCoords);
    return () => {
      window.removeEventListener('scroll', updateCoords, true);
      window.removeEventListener('resize', updateCoords);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => {
      if (btnRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <>
      <button ref={btnRef} className="btn btn-sm btn-ghost btn-icon" aria-label={label} aria-haspopup="menu" aria-expanded={open}
              onClick={() => setOpen((o) => !o)}>
        <MoreHorizontal />
      </button>
      {open && coords && createPortal(
        <div ref={menuRef} className="menu-pop menu-pop-fixed" role="menu" style={{ position: 'fixed', ...coords }}>
          {visibleItems.map((it) => (
            <button key={it.label} role="menuitem" onClick={() => { setOpen(false); it.onClick(); }} disabled={it.disabled}>
              {it.icon && <it.icon size={14} />} {it.label}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
