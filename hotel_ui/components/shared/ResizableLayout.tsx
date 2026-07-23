"use client";
import { useRef, useState, useCallback, useEffect } from "react";

interface Props {
  sidebar: React.ReactNode;
  main: React.ReactNode;
  defaultWidth?: number;
}

export default function ResizableLayout({ sidebar, main, defaultWidth = 280 }: Props) {
  const [sidebarWidth, setSidebarWidth] = useState(defaultWidth);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const handleRef = useRef<HTMLDivElement>(null);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true;
    startX.current = e.clientX;
    startWidth.current = sidebarWidth;
    handleRef.current?.classList.add("dragging");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [sidebarWidth]);

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      const next = Math.min(480, Math.max(180, startWidth.current + delta));
      setSidebarWidth(next);
    }
    function onMouseUp() {
      if (!dragging.current) return;
      dragging.current = false;
      handleRef.current?.classList.remove("dragging");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return (
    <div className="portal-layout">
      <aside className="portal-sidebar" style={{ width: sidebarWidth }}>
        {sidebar}
      </aside>
      <div
        ref={handleRef}
        className="resize-handle"
        onMouseDown={onMouseDown}
      />
      <main className="portal-main">
        {main}
      </main>
    </div>
  );
}
