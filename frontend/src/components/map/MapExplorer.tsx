"use client";

import { useEffect, useRef, useState } from "react";

import type { MapProductOptions } from "@/lib/types";

interface ExplorerModule {
  mount: (container: HTMLElement, options: MapProductOptions) => void;
}

type ExplorerWindow = Window & {
  __dynamicalExplorer?: ExplorerModule;
  __dynamicalExplorerPromise?: Promise<ExplorerModule>;
};

const EXPLORER_URL = "https://dynamical.org/explorer/explorer.js";

function loadExplorer(): Promise<ExplorerModule> {
  const explorerWindow = window as ExplorerWindow;
  if (explorerWindow.__dynamicalExplorer) {
    return Promise.resolve(explorerWindow.__dynamicalExplorer);
  }
  if (explorerWindow.__dynamicalExplorerPromise) {
    return explorerWindow.__dynamicalExplorerPromise;
  }

  const promise = new Promise<ExplorerModule>((resolve, reject) => {
    const script = document.createElement("script");
    script.type = "module";
    script.textContent = `
      import * as mod from "${EXPLORER_URL}";
      window.__dynamicalExplorer = mod;
      window.dispatchEvent(new Event("dynamical-explorer-ready"));
    `;

    let settled = false;
    const timer = window.setTimeout(() => {
      finish(new Error("The map library took too long to load."));
    }, 30_000);

    const cleanup = () => {
      window.clearTimeout(timer);
      window.removeEventListener("dynamical-explorer-ready", onReady);
      script.remove();
    };

    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      if (error) reject(error);
      else if (explorerWindow.__dynamicalExplorer) {
        resolve(explorerWindow.__dynamicalExplorer);
      } else {
        reject(new Error("The map library did not initialize."));
      }
    };

    const onReady = () => finish();

    window.addEventListener("dynamical-explorer-ready", onReady, {
      once: true,
    });
    script.addEventListener("error", () =>
      finish(new Error("The map library could not be downloaded.")),
    );
    document.head.appendChild(script);
  });

  explorerWindow.__dynamicalExplorerPromise = promise.catch((error) => {
    explorerWindow.__dynamicalExplorerPromise = undefined;
    throw error;
  });

  return explorerWindow.__dynamicalExplorerPromise;
}

export function MapExplorer({ options }: { options: MapProductOptions }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;

    setStatus("loading");
    setError(null);
    container.replaceChildren();

    loadExplorer()
      .then((explorer) => {
        if (cancelled) return;
        explorer.mount(container, options);
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setStatus("error");
        setError(reason instanceof Error ? reason.message : "The map library could not be loaded.");
      });

    return () => {
      cancelled = true;
    };
  }, [options]);

  return (
    <div
      className="relative w-full overflow-hidden rounded-md border border-white/10 bg-[#041016]"
      style={{ height: "min(72vh, 680px)" }}
    >
      <div ref={containerRef} className="h-full w-full" />
      {status === "loading" && (
        <div className="absolute inset-0 grid place-items-center bg-[#041016]/80">
          <div className="map-label text-xs text-[#86e4c7]">Loading map…</div>
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 grid place-items-center p-6 text-center">
          <div className="max-w-sm space-y-2">
            <div className="map-display text-lg text-[#e6f7f0]">Could not load the map</div>
            <p className="text-xs leading-relaxed text-[#86a39b]" role="alert">
              {error}
            </p>
            <a
              className="map-label inline-block text-xs text-[#86e4c7] underline underline-offset-4"
              href={`https://dynamical.org/catalog/${options.id}/`}
              target="_blank"
              rel="noreferrer"
            >
              Open this dataset on Dynamical
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
