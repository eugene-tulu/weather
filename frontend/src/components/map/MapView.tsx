"use client";

/* eslint-disable react-hooks/set-state-in-effect -- dataset metadata is loaded from the backend in an effect */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { MapExplorer } from "@/components/map/MapExplorer";
import { ApiError, fetchMapProduct } from "@/lib/api";
import { MAP_PRODUCTS } from "@/lib/map-products";
import type { MapProductOptions } from "@/lib/types";

export function MapView() {
  const [productId, setProductId] = useState(MAP_PRODUCTS[0].id);
  const [options, setOptions] = useState<MapProductOptions | null>(null);
  const [selectedVariable, setSelectedVariable] = useState("temperature_2m");
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [armed, setArmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const product = MAP_PRODUCTS.find((entry) => entry.id === productId) || MAP_PRODUCTS[0];

  useEffect(() => {
    const controller = new AbortController();
    setLoadingOptions(true);
    setError(null);
    setOptions(null);
    setArmed(false);

    fetchMapProduct(productId, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setOptions(result);
        setSelectedVariable(
          result.defaultVariable || result.variables[0]?.name || "temperature_2m",
        );
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof ApiError ? reason.message : "Could not load the map dataset metadata.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingOptions(false);
      });

    return () => controller.abort();
  }, [productId]);

  const effectiveOptions = useMemo(
    () => (options ? { ...options, defaultVariable: selectedVariable } : null),
    [options, selectedVariable],
  );

  const variableMeta = options?.variables.find((entry) => entry.name === selectedVariable);

  return (
    <div className="map-page min-h-screen">
      <header className="relative z-10 border-b border-white/10">
        <div className="mx-auto flex h-20 max-w-7xl items-center gap-3 px-4">
          <Link
            href="/"
            className="flex items-center gap-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#86e4c7]"
          >
            <span className="brand-mark" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <span className="map-label text-xs font-medium tracking-[0.18em] text-[#d9f4ea]">
              DISAGREEMENT <span className="text-[#54736b]">/ MAP</span>
            </span>
          </Link>
          <nav className="ml-auto flex items-center gap-5 text-xs text-[#86a39b]">
            <Link className="transition-colors hover:text-[#d9f4ea]" href="/">
              Time series
            </Link>
            <a
              className="transition-colors hover:text-[#d9f4ea]"
              href="https://dynamical.org/catalog/"
              target="_blank"
              rel="noreferrer"
            >
              Catalog ↗
            </a>
          </nav>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-7xl px-4 py-8 md:py-12">
        <section className="max-w-3xl">
          <div className="map-label flex items-center gap-2 text-[10px] text-[#75c6b1]">
            <span className="h-px w-7 bg-[#6ac8ad]" />
            Map-optimized datasets
          </div>
          <h1 className="map-display mt-4 text-4xl font-medium leading-[0.98] tracking-[-0.055em] text-[#edf7f2] md:text-6xl">
            See the weather move,
            <br />
            <span className="text-[#86e4c7]">not just a point.</span>
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-7 text-[#9ab3ad]">
            These are the catalog&apos;s virtual, map-optimized Icechunk datasets — aligned chunks
            for spatial reads. Pick a product and a surface variable. The WebGL explorer loads on
            demand.
          </p>
        </section>

        <div className="mt-8 grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
          <aside className="map-card h-fit rounded-lg p-5">
            <div className="map-label text-[10px] text-[#668b83]">Map source</div>

            <label className="mt-5 block" htmlFor="map-product">
              <span className="map-label text-[10px] text-[#94afa9]">Dataset</span>
              <select
                id="map-product"
                className="map-select mt-2"
                value={productId}
                onChange={(event) => setProductId(event.target.value)}
              >
                {MAP_PRODUCTS.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="mt-2 text-[10px] leading-5 text-[#5d7d76]">{product.description}</div>

            <label className="mt-5 block" htmlFor="map-variable">
              <span className="map-label text-[10px] text-[#94afa9]">Variable</span>
              <select
                id="map-variable"
                className="map-select mt-2"
                value={selectedVariable}
                onChange={(event) => setSelectedVariable(event.target.value)}
                disabled={!options || loadingOptions}
              >
                {(options?.variables || []).map((entry) => (
                  <option key={entry.name} value={entry.name}>
                    {entry.long_name}
                    {entry.units ? ` (${entry.units})` : ""}
                  </option>
                ))}
              </select>
            </label>

            {variableMeta && (
              <div className="mt-2 text-[10px] leading-5 text-[#5d7d76]">
                {variableMeta.name} · {variableMeta.dims.join(" × ")}
              </div>
            )}

            <div className="mt-5 grid grid-cols-2 gap-2 border-t border-white/10 pt-4">
              <div>
                <div className="map-label text-[9px] text-[#54726c]">Domain</div>
                <div className="mt-1 font-mono text-[11px] text-[#aed2c8]">{product.domain}</div>
              </div>
              <div>
                <div className="map-label text-[9px] text-[#54726c]">Resolution</div>
                <div className="mt-1 font-mono text-[11px] text-[#aed2c8]">
                  {product.resolution}
                </div>
              </div>
              <div className="col-span-2">
                <div className="map-label text-[9px] text-[#54726c]">Cadence</div>
                <div className="mt-1 font-mono text-[11px] text-[#aed2c8]">{product.cadence}</div>
              </div>
            </div>

            <button
              type="button"
              className="map-button mt-6 w-full"
              onClick={() => setArmed(true)}
              disabled={!options || loadingOptions}
            >
              {loadingOptions
                ? "Loading metadata…"
                : armed
                  ? "Reload interactive map"
                  : "Load interactive map"}
            </button>

            <p className="mt-3 text-center text-[9px] leading-4 text-[#53706a]">
              Loads the deck.gl explorer (~1.5 MB) from dynamical.org. Map reads are spatial
              Icechunk reads, separate from the point API.
            </p>

            {error && (
              <div
                className="mt-4 rounded border border-red-400/25 bg-red-500/10 px-3 py-2 text-[11px] leading-5 text-[#f1ad99]"
                role="alert"
              >
                {error}
              </div>
            )}

            <a
              className="map-label mt-4 block text-center text-[9px] text-[#73cbb0] underline underline-offset-4"
              href={`https://dynamical.org/catalog/${productId}/`}
              target="_blank"
              rel="noreferrer"
            >
              Dataset documentation ↗
            </a>
          </aside>

          <section className="map-card rounded-lg p-3 md:p-4">
            <div className="mb-3 flex items-start justify-between gap-4 px-1">
              <div>
                <h2 className="map-display text-xl font-medium tracking-[-0.03em] text-[#e6f7f0]">
                  {product.label}
                  <span className="ml-2 font-mono text-[10px] tracking-normal text-[#668c85]">
                    {product.resolution}
                  </span>
                </h2>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-[#6d8b85]">
                  <span className="map-dot" />
                  {loadingOptions
                    ? "Reading dataset metadata"
                    : armed
                      ? "Map explorer mounted"
                      : "Preview — load to explore"}
                </div>
              </div>
              <div className="map-label text-right text-[9px] text-[#54726c]">
                {options ? `${options.variables.length} variables` : "—"}
              </div>
            </div>

            {armed && effectiveOptions ? (
              <MapExplorer options={effectiveOptions} />
            ) : (
              <div className="map-preview-grid relative grid min-h-[420px] place-items-center overflow-hidden rounded-md border border-white/10 bg-[#041016] md:min-h-[560px]">
                <div className="relative z-10 max-w-sm px-6 text-center">
                  <div className="map-label text-[10px] text-[#76d0b4]">Spatial preview</div>
                  <div className="map-display mt-4 text-2xl font-medium tracking-[-0.04em] text-[#e0f5ed]">
                    {product.label}
                  </div>
                  <p className="mt-3 text-[11px] leading-6 text-[#82a29a]">
                    The global field, ensemble members, and lead-time controls are rendered in the
                    interactive map. The preview stays lightweight until you load it.
                  </p>
                  <button
                    type="button"
                    className="map-button mt-5"
                    onClick={() => setArmed(true)}
                    disabled={!options || loadingOptions}
                  >
                    {loadingOptions ? "Loading…" : "Load interactive map"}
                  </button>
                </div>
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-[9px] text-[#55716d]">
              <span>
                Icechunk virtual dataset · deck.gl · {variableMeta?.long_name || "surface variable"}
              </span>
              <span>Attribution: NOAA / ECMWF via Dynamical</span>
            </div>
          </section>
        </div>
      </main>

      <footer className="relative z-10 border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-5 text-[10px] text-[#5e7d76]">
          <span>
            Data: NOAA GFS/GEFS, ECMWF AIFS/IFS ENS via{" "}
            <a
              className="text-[#73cbb0] underline underline-offset-4"
              href="https://dynamical.org/catalog/"
              target="_blank"
              rel="noreferrer"
            >
              Dynamical
            </a>
            .
          </span>
          <Link className="text-[#73cbb0] underline underline-offset-4" href="/">
            Back to point forecasts
          </Link>
        </div>
      </footer>
    </div>
  );
}
