"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  src: string;
  alt: string;
  locale?: "pt-BR" | "en-US";
};

const MIN_SCALE = 1;
const MAX_SCALE = 5;
const SCALE_STEP = 0.5;

export function ImageLightbox({ src, alt, locale = "pt-BR" }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const pointersRef = useRef(new Map<number, { x: number; y: number }>());
  const pinchDistanceRef = useRef<number | null>(null);
  const dragRef = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);
  const [open, setOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [failed, setFailed] = useState(false);
  const english = locale === "en-US";

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previousOverflow = document.body.style.overflow;

    if (open) {
      dialog.showModal();
      document.body.style.overflow = "hidden";
      dialog.querySelector<HTMLButtonElement>(".snbr-lightbox-close")?.focus();
    }

    return () => {
      document.body.style.overflow = previousOverflow;
      if (dialog.open) dialog.close();
    };
  }, [open]);

  function close() {
    setOpen(false);
    setScale(1);
    setOffset({ x: 0, y: 0 });
    pointersRef.current.clear();
    window.setTimeout(() => openerRef.current?.focus(), 0);
  }

  function updateScale(next: number) {
    const value = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next));
    setScale(value);
    if (value === 1) setOffset({ x: 0, y: 0 });
  }

  function pointerDistance() {
    const [first, second] = Array.from(pointersRef.current.values());
    return first && second ? Math.hypot(second.x - first.x, second.y - first.y) : null;
  }

  return (
    <>
      <button
        ref={openerRef}
        className="snbr-image-trigger"
        type="button"
        aria-label={english ? "Enlarge image" : "Ampliar imagem"}
        onClick={() => setOpen(true)}
      >
        {failed ? <span className="snbr-image-fallback">{english ? "Image unavailable" : "Imagem indisponível"}</span> : <img className="snbr-image" src={src} alt={alt} onError={() => setFailed(true)} />}
      </button>

      <dialog
        ref={dialogRef}
        className="snbr-lightbox"
        aria-label={english ? "Image viewer" : "Visualizador de imagem"}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      >
        <div className="snbr-lightbox-toolbar">
          <button type="button" onClick={() => updateScale(scale - SCALE_STEP)} disabled={scale <= MIN_SCALE} aria-label={english ? "Zoom out" : "Diminuir zoom"}>−</button>
          <button type="button" onClick={() => updateScale(1)} aria-label={english ? "Restore 100%" : "Restaurar 100%"}>{Math.round(scale * 100)}%</button>
          <button type="button" onClick={() => updateScale(scale + SCALE_STEP)} disabled={scale >= MAX_SCALE} aria-label={english ? "Zoom in" : "Aumentar zoom"}>+</button>
          <button className="snbr-lightbox-close" type="button" onClick={close} aria-label={english ? "Close image viewer" : "Fechar visualizador de imagem"}>×</button>
        </div>
        <div
          className="snbr-lightbox-stage"
          onClick={(event) => {
            if (event.target === event.currentTarget) close();
          }}
          onWheel={(event) => {
            event.preventDefault();
            updateScale(scale + (event.deltaY < 0 ? SCALE_STEP : -SCALE_STEP));
          }}
          onDoubleClick={() => updateScale(scale === 1 ? 2 : 1)}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
            pinchDistanceRef.current = pointerDistance();
            if (scale > 1 && pointersRef.current.size === 1) dragRef.current = { x: event.clientX, y: event.clientY, offsetX: offset.x, offsetY: offset.y };
          }}
          onPointerMove={(event) => {
            if (!pointersRef.current.has(event.pointerId)) return;
            pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
            const distance = pointerDistance();
            if (distance && pinchDistanceRef.current) {
              updateScale(scale * (distance / pinchDistanceRef.current));
              pinchDistanceRef.current = distance;
            } else if (dragRef.current && scale > 1) {
              setOffset({ x: dragRef.current.offsetX + event.clientX - dragRef.current.x, y: dragRef.current.offsetY + event.clientY - dragRef.current.y });
            }
          }}
          onPointerUp={(event) => {
            pointersRef.current.delete(event.pointerId);
            pinchDistanceRef.current = pointerDistance();
            dragRef.current = null;
          }}
          onPointerCancel={(event) => {
            pointersRef.current.delete(event.pointerId);
            pinchDistanceRef.current = pointerDistance();
            dragRef.current = null;
          }}
        >
          {failed ? <p className="snbr-image-fallback">{english ? "The image could not be loaded." : "Não foi possível carregar a imagem."}</p> : (
            <img
              className="snbr-lightbox-image"
              src={src}
              alt={alt}
              draggable={false}
              style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
              onError={() => setFailed(true)}
              onClick={(event) => event.stopPropagation()}
            />
          )}
        </div>
      </dialog>
    </>
  );
}
