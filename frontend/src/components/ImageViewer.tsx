// Full-screen image viewer for checking generation details.
// Fit-to-screen by default; click (or scroll) to zoom, drag to pan,
// arrow keys to move between images, Escape to close.
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export interface ViewerImage {
  src: string;
  caption: string;
}

interface Props {
  images: ViewerImage[];
  index: number;
  onIndexChange?: (index: number) => void; // omit for a single image
  onClose: () => void;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;
const CLICK_ZOOM = 2.5;

export default function ImageViewer({ images, index, onIndexChange, onClose }: Props) {
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const { zoom } = view;
  const drag = useRef<{ x: number; y: number; panX: number; panY: number; moved: boolean; onImage: boolean } | null>(
    null,
  );
  const stage = useRef<HTMLDivElement>(null);
  const image = images[index];

  const reset = useCallback(() => setView({ zoom: 1, x: 0, y: 0 }), []);

  const go = useCallback(
    (step: number) => {
      if (images.length < 2) return;
      onIndexChange?.((index + step + images.length) % images.length);
      reset();
    },
    [images.length, index, onIndexChange, reset],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight') go(1);
      else if (e.key === 'ArrowLeft') go(-1);
      else if (e.key === '0') reset();
    };
    window.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
    };
  }, [go, onClose, reset]);

  // Zoom toward a screen point, so the detail under the cursor stays put.
  const zoomAt = useCallback((next: (zoom: number) => number, clientX: number, clientY: number) => {
    const rect = stage.current?.getBoundingClientRect();
    if (!rect) return;
    const cx = clientX - rect.left - rect.width / 2;
    const cy = clientY - rect.top - rect.height / 2;
    setView((v) => {
      const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next(v.zoom)));
      if (z === 1) return { zoom: 1, x: 0, y: 0 };
      return { zoom: z, x: cx - ((cx - v.x) * z) / v.zoom, y: cy - ((cy - v.y) * z) / v.zoom };
    });
  }, []);

  // Non-passive wheel listener so the page doesn't scroll behind the viewer.
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomAt((z) => z * Math.exp(-e.deltaY * 0.002), e.clientX, e.clientY);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoomAt]);

  if (!image) return null;

  return createPortal(
    <div className="viewer" role="dialog" aria-modal="true" aria-label={image.caption}>
      <div className="viewer-bar">
        <span className="viewer-caption">
          {image.caption}
          {images.length > 1 && (
            <span className="viewer-count">
              {' '}
              · {index + 1} of {images.length}
            </span>
          )}
        </span>
        <span className="viewer-zoom">{Math.round(zoom * 100)}%</span>
        <button type="button" onClick={reset} disabled={zoom === 1}>
          Fit
        </button>
        <a href={image.src} target="_blank" rel="noreferrer">
          Open full size
        </a>
        <button type="button" onClick={onClose} aria-label="Close viewer">
          ✕
        </button>
      </div>

      <div
        ref={stage}
        className={`viewer-stage${zoom > 1 ? ' viewer-stage--zoomed' : ''}`}
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          // Pointer capture retargets pointerup to the stage, so note now what was pressed.
          const onImage = e.target !== e.currentTarget;
          drag.current = { x: e.clientX, y: e.clientY, panX: view.x, panY: view.y, moved: false, onImage };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const dx = e.clientX - d.x;
          const dy = e.clientY - d.y;
          if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true;
          if (d.moved && zoom > 1) setView((v) => ({ ...v, x: d.panX + dx, y: d.panY + dy }));
        }}
        onPointerUp={(e) => {
          const d = drag.current;
          drag.current = null;
          if (!d || d.moved) return;
          // A click on the dark backdrop closes; a click on the image zooms.
          if (!d.onImage && zoom === 1) onClose();
          else if (zoom === 1) zoomAt(() => CLICK_ZOOM, e.clientX, e.clientY);
          else reset();
        }}
      >
        <img
          key={image.src}
          src={image.src}
          alt={image.caption}
          draggable={false}
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${zoom})` }}
        />
      </div>

      {images.length > 1 && (
        <>
          <button type="button" className="viewer-nav viewer-nav--prev" onClick={() => go(-1)} aria-label="Previous image">
            ‹
          </button>
          <button type="button" className="viewer-nav viewer-nav--next" onClick={() => go(1)} aria-label="Next image">
            ›
          </button>
        </>
      )}
      <div className="viewer-help">Click or scroll to zoom · drag to move · ← → next · Esc close</div>
    </div>,
    document.body,
  );
}
