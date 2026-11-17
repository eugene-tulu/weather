"use client";

/* eslint-disable react-hooks/set-state-in-effect -- URL, theme, and external fetch state are synchronized from effects */

import Link from "next/link";
import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Area, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ChartContainer } from "@/components/ui/chart";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ApiError, fetchAnalysis, fetchForecast, fetchGeocode, fetchRuns } from "@/lib/api";
import { buildChartData, computeStats, formatRunAge, toCsv, valueAtTime } from "@/lib/forecast";
import { COLORS, MODEL_VARIABLES, MODELS, VARS, modelLabel } from "@/lib/models";
import { normalizeResult } from "@/lib/normalize";
import type { ApiResult, GeocodeResult, NormalizedResult, RunOption } from "@/lib/types";
import { useFocusTrap } from "@/lib/useFocusTrap";

const DEFAULT_MODELS = [
  "noaa-gfs-forecast",
  "noaa-hrrr-forecast-48-hour",
  "noaa-gefs-forecast-35-day",
  "noaa-gfs-analysis",
];

const TAB_ORDER = ["fan", "spaghetti", "agreement", "table"] as const;
type Tab = (typeof TAB_ORDER)[number];

export default function Page() {
  const [lat, setLat] = useState("41.8781");
  const [lon, setLon] = useState("-87.6298");
  const [q, setQ] = useState("");
  const [suggestions, setSuggestions] = useState<GeocodeResult[]>([]);
  const [variable, setVariable] = useState("temperature_2m");
  const [models, setModels] = useState<string[]>(DEFAULT_MODELS);
  const [maxLead, setMaxLead] = useState(48);
  const [snapshot, setSnapshot] = useState("latest");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [showHowTo, setShowHowTo] = useState(false);
  const [data, setData] = useState<{ results: ApiResult[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [runOptions, setRunOptions] = useState<RunOption[]>([]);
  const [latestInitTime, setLatestInitTime] = useState<string | undefined>();
  const [railOpen, setRailOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("fan");
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [urlReady, setUrlReady] = useState(false);
  const [themeReady, setThemeReady] = useState(false);

  const modalRef = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLElement>(null);
  const previousPrimary = useRef<string | undefined>(undefined);

  const varMeta = VARS.find((v) => v.id === variable) || VARS[0];

  const availableVariableIds = useMemo(() => {
    const available = new Set<string>();
    for (const entry of VARS) {
      if (models.some((id) => MODEL_VARIABLES[id]?.includes(entry.id))) {
        available.add(entry.id);
      }
    }
    return available;
  }, [models]);

  const unsupportedSelected = useMemo(
    () => models.filter((id) => !MODEL_VARIABLES[id]?.includes(variable)).map(modelLabel),
    [models, variable],
  );

  const results = useMemo<NormalizedResult[]>(
    () =>
      (data?.results ?? [])
        .filter((result) => !result.status || result.status === "ok")
        .map((result) => normalizeResult(result)),
    [data],
  );

  const stats = useMemo(
    () => (results.length ? computeStats(results, variable, varMeta.scale) : null),
    [results, variable, varMeta.scale],
  );

  const chartData = useMemo(
    () => (results.length ? buildChartData(results, variable) : []),
    [results, variable],
  );

  const errorResults = useMemo(
    () => (data?.results ?? []).filter((result) => result.status === "error"),
    [data],
  );

  const ensembleMemberCount = useMemo(
    () => results.reduce((total, result) => total + (result._ensemble?.length || 0), 0),
    [results],
  );

  const primaryModel = models[0];

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    const latParam = params.get("lat");
    if (latParam !== null) {
      const value = Number(latParam);
      if (Number.isFinite(value) && value >= -90 && value <= 90) {
        setLat(String(value));
      }
    }

    const lonParam = params.get("lon");
    if (lonParam !== null) {
      const value = Number(lonParam);
      if (Number.isFinite(value) && value >= -180 && value <= 180) {
        setLon(String(value));
      }
    }

    const variableParam = params.get("v");
    if (variableParam && VARS.some((v) => v.id === variableParam)) {
      setVariable(variableParam);
    }

    const modelIds = (params.get("models") || "")
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean);
    const validModels = modelIds.filter((id) => MODELS.some((model) => model.id === id));
    if (validModels.length) {
      setModels(Array.from(new Set(validModels)));
    }

    const leadParam = params.get("lead");
    if (leadParam !== null) {
      const value = Number(leadParam);
      if (Number.isFinite(value)) {
        setMaxLead(Math.min(840, Math.max(6, Math.round(value / 6) * 6)));
      }
    }

    const snapshotParam = params.get("snap");
    if (
      snapshotParam === "latest" ||
      (snapshotParam && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(snapshotParam))
    ) {
      setSnapshot(snapshotParam);
    }

    const themeParam = params.get("theme");
    if (themeParam === "light" || themeParam === "dark") {
      setTheme(themeParam);
      setThemeReady(true);
    }

    setUrlReady(true);
  }, []);

  useEffect(() => {
    if (themeReady) return;
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("theme");
    } catch {
      stored = null;
    }
    const initial =
      stored === "light" || stored === "dark"
        ? stored
        : document.documentElement.classList.contains("dark")
          ? "dark"
          : "light";
    setTheme(initial);
    setThemeReady(true);
  }, [themeReady]);

  useEffect(() => {
    if (!themeReady) return;
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // Storage can be unavailable in private contexts.
    }
  }, [theme, themeReady]);

  useEffect(() => {
    if (!urlReady) return;
    const params = new URLSearchParams();
    params.set("lat", lat);
    params.set("lon", lon);
    params.set("v", variable);
    params.set("models", models.join(","));
    params.set("lead", String(maxLead));
    params.set("snap", snapshot);
    params.set("theme", theme);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [urlReady, lat, lon, variable, models, maxLead, snapshot, theme]);

  useEffect(() => {
    if (!primaryModel) {
      setRunOptions([]);
      setLatestInitTime(undefined);
      return;
    }

    const controller = new AbortController();
    void (async () => {
      try {
        const result = await fetchRuns(primaryModel, controller.signal);
        if (controller.signal.aborted) return;
        const options = result.runs ?? [];
        setRunOptions(options);
        setLatestInitTime(options[0]?.initTime);
      } catch (reason) {
        if (controller.signal.aborted) return;
        if (reason instanceof ApiError && reason.status === 0) return;
        setRunOptions([]);
        setLatestInitTime(undefined);
      }
    })();

    return () => controller.abort();
  }, [primaryModel]);

  useEffect(() => {
    if (previousPrimary.current !== undefined && previousPrimary.current !== primaryModel) {
      setSnapshot("latest");
    }
    previousPrimary.current = primaryModel;
  }, [primaryModel]);

  useEffect(() => {
    if (
      snapshot !== "latest" &&
      runOptions.length > 0 &&
      !runOptions.some((option) => option.initTime === snapshot)
    ) {
      setSnapshot("latest");
    }
  }, [runOptions, snapshot]);

  useEffect(() => {
    if (!models.length) return;

    const dropped = models.filter((id) => {
      const model = MODELS.find((entry) => entry.id === id);
      return !model || (model.type !== "Analysis" && model.horizon < maxLead);
    });
    if (!dropped.length) return;

    const kept = models.filter((id) => !dropped.includes(id));
    setModels(kept);
    setNotice(`${dropped.map(modelLabel).join(", ")} dropped: horizon shorter than ${maxLead}h.`);
  }, [maxLead, models]);

  useEffect(() => {
    if (!models.length || availableVariableIds.has(variable)) return;
    const fallback = availableVariableIds.has("temperature_2m")
      ? "temperature_2m"
      : VARS.find((entry) => availableVariableIds.has(entry.id))?.id;
    if (!fallback) return;
    setVariable(fallback);
    setNotice(
      `Switched to ${VARS.find((entry) => entry.id === fallback)?.label}: ${varMeta.label} is not available for the selected models.`,
    );
  }, [availableVariableIds, models, variable, varMeta.label]);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) {
      setSuggestions([]);
      setGeoError(null);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const result = await fetchGeocode(query, controller.signal);
          if (controller.signal.aborted) return;
          setSuggestions(result.results ?? []);
          setGeoError(null);
        } catch (reason) {
          if (controller.signal.aborted) return;
          if (reason instanceof ApiError && reason.status === 0) return;
          setSuggestions([]);
          setGeoError("Could not search locations.");
        }
      })();
    }, 300);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q]);

  useEffect(() => {
    if (!urlReady) return;

    const controller = new AbortController();
    const timer = setTimeout(() => {
      void (async () => {
        if (models.length === 0) {
          setData(null);
          setLoading(false);
          setError("Select at least one model.");
          return;
        }

        const latitude = Number(lat);
        const longitude = Number(lon);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
          setData(null);
          setLoading(false);
          setError("Coordinates are not valid.");
          return;
        }

        setLoading(true);
        setError(null);
        setData(null);

        const forecastModels = models.filter(
          (id) => !id.includes("analysis") && MODEL_VARIABLES[id]?.includes(variable),
        );
        const analysisModels = models.filter(
          (id) => id.includes("analysis") && MODEL_VARIABLES[id]?.includes(variable),
        );
        const fetchVariables =
          variable === "wind_speed" ? ["wind_u_10m", "wind_v_10m"] : [variable];
        const initTime = snapshot === "latest" ? undefined : snapshot;

        const pointBody = {
          latitude,
          longitude,
          products: forecastModels,
          variables: fetchVariables,
          maxLeadTimeHours: maxLead,
          ...(initTime ? { initTime } : {}),
        };

        const requestedAnalysisStart =
          snapshot === "latest"
            ? latestInitTime || new Date(Date.now() - 3_600_000).toISOString()
            : snapshot;
        const requestedStartMs = new Date(requestedAnalysisStart).getTime();
        const analysisStartMs =
          Number.isFinite(requestedStartMs) && requestedStartMs < Date.now()
            ? requestedStartMs
            : Date.now() - 3_600_000;
        const analysisStartTime = new Date(analysisStartMs).toISOString();
        const analysisEndMs = Math.min(
          Date.now(),
          analysisStartMs + maxLead * 3_600_000,
          analysisStartMs + 31 * 24 * 3_600_000,
        );
        const analysisEnd = new Date(analysisEndMs).toISOString();

        const analysisBody = {
          latitude,
          longitude,
          products: analysisModels,
          variables: fetchVariables,
          startTime: analysisStartTime,
          endTime: analysisEnd,
        };

        try {
          const [pointResult, analysisResult] = await Promise.all([
            forecastModels.length
              ? fetchForecast(pointBody, controller.signal)
              : Promise.resolve({ results: [] as ApiResult[] }),
            analysisModels.length
              ? fetchAnalysis(analysisBody, controller.signal)
              : Promise.resolve({ results: [] as ApiResult[] }),
          ]);

          if (controller.signal.aborted) return;
          setData({
            results: [...(pointResult.results ?? []), ...(analysisResult.results ?? [])],
          });
        } catch (reason) {
          if (controller.signal.aborted) return;
          if (reason instanceof ApiError) {
            setError(reason.status === 0 ? "Request timed out. Try again." : reason.message);
          } else {
            setError(reason instanceof Error ? reason.message : "Could not load forecast.");
          }
          setData(null);
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      })();
    }, 400);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [urlReady, lat, lon, variable, models, maxLead, snapshot, latestInitTime]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 3_000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!copyStatus) return;
    const timer = setTimeout(() => setCopyStatus(null), 2_000);
    return () => clearTimeout(timer);
  }, [copyStatus]);

  const closeModal = useCallback(() => setShowHowTo(false), []);
  const closeRail = useCallback(() => setRailOpen(false), []);

  useFocusTrap(showHowTo, modalRef, closeModal);
  useFocusTrap(railOpen && !showHowTo, railRef, closeRail);

  const toggleModel = useCallback((id: string) => {
    setModels((previous) =>
      previous.includes(id) ? previous.filter((entry) => entry !== id) : [...previous, id],
    );
    setNotice(null);
  }, []);

  const handleUseMyLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoError("Geolocation is not available in this browser.");
      return;
    }

    setLocating(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLat(position.coords.latitude.toFixed(4));
        setLon(position.coords.longitude.toFixed(4));
        setQ("");
        setSuggestions([]);
        setLocating(false);
      },
      (positionError) => {
        setGeoError(
          positionError.code === positionError.PERMISSION_DENIED
            ? "Location permission denied."
            : "Could not get your location.",
        );
        setLocating(false);
      },
      {
        enableHighAccuracy: false,
        timeout: 10_000,
        maximumAge: 300_000,
      },
    );
  }, []);

  const copyText = useCallback(async (text: string, label: string) => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(text);
      setCopyStatus(`${label} copied`);
    } catch {
      setCopyStatus("Copy failed");
    }
  }, []);

  const copyJson = useCallback(() => {
    if (!data) return;
    void copyText(JSON.stringify(data, null, 2), "JSON");
  }, [copyText, data]);

  const copyLink = useCallback(() => {
    void copyText(window.location.href, "Link");
  }, [copyText]);

  const downloadCsv = useCallback(() => {
    if (!results.length) return;
    const csv = toCsv(results, variable, modelLabel);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "forecast.csv";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1_000);
  }, [results, variable]);

  const onTabKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const nextIndex =
      event.key === "ArrowRight"
        ? (index + 1) % TAB_ORDER.length
        : (index - 1 + TAB_ORDER.length) % TAB_ORDER.length;
    const nextTab = TAB_ORDER[nextIndex];
    setTab(nextTab);
    document.getElementById(`tab-${nextTab}`)?.focus();
  };

  const spreadSummary = stats
    ? `${stats.spreadAt(24)} / ${stats.spreadAt(72)} / ${stats.spreadAt(168)} ${varMeta.unit}`
    : "—";

  const runAgeSummary = stats
    ? stats.runAges.map((run) => `${modelLabel(run.id)}: ${formatRunAge(run.time)}`).join(" · ")
    : "—";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
          <div className="size-8 rounded bg-primary text-primary-foreground grid place-items-center font-bold">
            Δ
          </div>
          <div>
            <h1 className="font-bold tracking-tight leading-none">Disagreement</h1>
            <div className="text-xs text-muted-foreground">
              Weather isn&apos;t a number. It&apos;s a disagreement.
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Link
              href="/map"
              className="hidden h-8 items-center rounded-md border border-border px-3 text-sm font-medium hover:bg-accent/10 focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex"
            >
              Map
            </Link>
            <Button variant="outline" size="sm" onClick={() => setShowHowTo(true)}>
              How to read this
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? "Light" : "Dark"}
            </Button>
            <Button
              className="md:hidden focus-visible:ring-2 focus-visible:ring-ring"
              variant="outline"
              size="sm"
              onClick={() => setRailOpen((open) => !open)}
              aria-expanded={railOpen}
              aria-controls="forecast-controls"
            >
              {railOpen ? "Close" : "Controls"}
            </Button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl w-full mx-auto px-4 py-4 grid grid-cols-1 md:grid-cols-[300px_minmax(0,1fr)] gap-4 flex-1">
        <aside
          id="forecast-controls"
          ref={railRef}
          role={railOpen ? "dialog" : "region"}
          aria-modal={railOpen ? "true" : undefined}
          aria-label="Forecast controls"
          className={`${
            railOpen ? "block" : "hidden"
          } md:block max-md:col-span-1 max-md:sticky max-md:bottom-[57px] max-md:z-20 max-md:bg-background max-md:pb-2 max-h-[inherit]`}
        >
          <Card>
            <CardContent className="p-3 space-y-3">
              <div className="flex items-center justify-between md:hidden">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Controls
                </div>
                <Button variant="ghost" size="sm" onClick={closeRail}>
                  Close
                </Button>
              </div>
              <div>
                <label
                  htmlFor="location-search"
                  className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Location
                </label>
                <div className="flex gap-1 mt-1">
                  <Input
                    id="location-search"
                    value={q}
                    onChange={(event) => setQ(event.target.value)}
                    placeholder="Search city…"
                    role="combobox"
                    aria-expanded={suggestions.length > 0}
                    aria-controls="geocode-results"
                    aria-autocomplete="list"
                    aria-label="Search city"
                    className="focus-visible:ring-2 focus-visible:ring-ring"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleUseMyLocation}
                    disabled={locating}
                  >
                    {locating ? "Locating…" : "Use my location"}
                  </Button>
                </div>
                {geoError && (
                  <div className="text-xs text-destructive mt-1" role="alert">
                    {geoError}
                  </div>
                )}
                {suggestions.length > 0 && (
                  <div
                    id="geocode-results"
                    role="listbox"
                    aria-label="Location suggestions"
                    className="mt-1 border border-border rounded max-h-40 overflow-auto bg-popover"
                  >
                    {suggestions.map((suggestion) => (
                      <button
                        key={
                          suggestion.id ??
                          `${suggestion.name}-${suggestion.latitude}-${suggestion.longitude}`
                        }
                        type="button"
                        role="option"
                        aria-selected={false}
                        className="block w-full text-left px-2 py-1 text-sm hover:bg-accent/10 focus-visible:bg-accent/10 focus-visible:outline-none"
                        onClick={() => {
                          setLat(String(suggestion.latitude));
                          setLon(String(suggestion.longitude));
                          setQ(suggestion.name);
                          setSuggestions([]);
                          setGeoError(null);
                        }}
                      >
                        {suggestion.name}
                        {suggestion.admin1 || suggestion.country
                          ? `, ${[suggestion.admin1, suggestion.country].filter(Boolean).join(", ")}`
                          : ""}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="text-[10.5px] text-muted-foreground font-mono">
                {lat}, {lon}
              </div>

              <div className="flex flex-wrap gap-1">
                {[
                  { label: "Chicago", lat: "41.8781", lon: "-87.6298" },
                  { label: "NYC", lat: "40.7128", lon: "-74.0060" },
                  { label: "London", lat: "51.5072", lon: "-0.1276" },
                  { label: "Tokyo", lat: "35.6762", lon: "139.6503" },
                  { label: "Sydney", lat: "-33.8688", lon: "151.2093" },
                ].map((city) => (
                  <button
                    key={city.label}
                    type="button"
                    onClick={() => {
                      setLat(city.lat);
                      setLon(city.lon);
                      setQ(city.label);
                      setSuggestions([]);
                    }}
                    className="text-xs px-2 py-1 rounded border border-border hover:bg-accent/10 focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {city.label}
                  </button>
                ))}
              </div>

              <div>
                <div className="text-xs font-semibold text-muted-foreground uppercase mb-1">
                  Variable
                </div>
                <div className="grid grid-cols-2 gap-1">
                  {VARS.map((entry) => {
                    const available = availableVariableIds.has(entry.id);
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        disabled={!available}
                        onClick={() => available && setVariable(entry.id)}
                        title={
                          available
                            ? entry.label
                            : `${entry.label} is not provided by the selected models`
                        }
                        className={`text-xs px-2 py-1 rounded border focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-35 ${
                          variable === entry.id
                            ? "bg-primary text-primary-foreground border-primary"
                            : "border-border hover:bg-accent/10"
                        }`}
                      >
                        {entry.label}
                      </button>
                    );
                  })}
                </div>
                {unsupportedSelected.length > 0 && (
                  <div className="text-[10.5px] text-muted-foreground mt-1">
                    {unsupportedSelected.join(", ")} excluded: this dataset has no{" "}
                    {varMeta.label.toLowerCase()}.
                  </div>
                )}
              </div>

              <div>
                <div className="text-xs font-semibold text-muted-foreground uppercase mb-1">
                  Models
                </div>
                {(["Deterministic", "Ensemble", "Analysis"] as const).map((group) => (
                  <div key={group} className="mb-2">
                    <div className="text-xs text-muted-foreground mb-1">{group}</div>
                    {MODELS.filter((model) => model.type === group).map((model) => {
                      const available = model.type === "Analysis" || model.horizon >= maxLead;
                      return (
                        <div
                          key={model.id}
                          className={`flex items-start gap-2 text-xs mb-1 ${
                            available ? "" : "opacity-40"
                          }`}
                        >
                          <Checkbox
                            checked={models.includes(model.id)}
                            disabled={!available}
                            onCheckedChange={() => {
                              if (available) toggleModel(model.id);
                            }}
                            aria-label={model.label}
                            className="mt-0.5"
                          />
                          <button
                            type="button"
                            className="text-left focus-visible:ring-2 focus-visible:ring-ring"
                            disabled={!available}
                            onClick={() => {
                              if (available) toggleModel(model.id);
                            }}
                            title={available ? "" : `${model.label} does not reach ${maxLead}h`}
                          >
                            <span className="font-medium">{model.label}</span>
                            <span className="block text-[10.5px] text-muted-foreground leading-snug">
                              {model.desc} · <span className="font-mono">≤{model.horizon}h</span>
                            </span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>

              <div>
                <label
                  htmlFor="lead-time"
                  className="text-xs font-semibold text-muted-foreground uppercase"
                >
                  Forecast horizon
                </label>
                <input
                  id="lead-time"
                  type="range"
                  min={6}
                  max={840}
                  step={6}
                  value={maxLead}
                  onChange={(event) => setMaxLead(Number(event.target.value))}
                  className="w-full mt-1 focus-visible:ring-2 focus-visible:ring-ring"
                  aria-valuetext={`${maxLead} hours`}
                />
                <div className="text-xs text-muted-foreground mt-1">0 → {maxLead}h</div>
              </div>

              <div>
                <label
                  htmlFor="snapshot"
                  className="text-xs font-semibold text-muted-foreground uppercase"
                >
                  Snapshot / run
                </label>
                <select
                  id="snapshot"
                  className="w-full mt-1 border border-border rounded px-2 py-1 bg-background text-sm focus-visible:ring-2 focus-visible:ring-ring"
                  value={snapshot}
                  onChange={(event) => setSnapshot(event.target.value)}
                >
                  <option value="latest">Latest available run</option>
                  {runOptions.map((option) => (
                    <option key={option.initTime} value={option.initTime}>
                      {option.initTime.replace("T", " ").replace("Z", "")}
                    </option>
                  ))}
                </select>
              </div>
            </CardContent>
          </Card>
        </aside>

        <main className="min-w-0 space-y-4">
          {error && (
            <div
              role="alert"
              className="rounded border border-destructive/30 bg-destructive/10 text-destructive text-sm px-3 py-2"
            >
              {error}
            </div>
          )}
          {notice && (
            <div
              role="status"
              className="rounded border border-border bg-muted/50 text-xs px-3 py-2"
            >
              {notice}
            </div>
          )}

          <Card>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                {ensembleMemberCount > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {ensembleMemberCount} ensemble members pooled
                  </span>
                )}
                {loading && (
                  <span className="text-xs text-muted-foreground" role="status">
                    Fetching…
                  </span>
                )}
              </div>

              <div className="flex items-start gap-4 flex-wrap">
                <div className="min-w-[110px]">
                  <div className="text-xs text-muted-foreground">Confidence</div>
                  <div className="text-3xl font-bold tabular-nums">
                    {stats ? stats.score : "—"}
                    <span className="text-sm text-muted-foreground">/100</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {stats ? stats.label : "select models"}
                  </div>
                </div>

                <div className="flex-1 min-w-[240px] text-sm">
                  {stats ? (
                    <>
                      <div className="text-sm text-muted-foreground mb-1">
                        Models agree within{" "}
                        <span className="text-foreground font-semibold">
                          {stats.thr.toFixed(1)}
                        </span>{" "}
                        {varMeta.unit} of each other through{" "}
                        <span className="text-foreground font-semibold">
                          {stats.agreeUntil >= 24
                            ? `${Math.round(stats.agreeUntil / 24)}d`
                            : `${stats.agreeUntil}h`}
                        </span>
                        {stats.maxSplit > 0 ? (
                          <>
                            {" "}
                            then split by up to{" "}
                            <span className="text-foreground font-semibold">
                              {stats.maxSplit.toFixed(1)}
                            </span>{" "}
                            {varMeta.unit}
                          </>
                        ) : null}
                        .
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Ensemble spread + inter-model deviation vs. a {varMeta.unit} threshold. No
                        one model is marked right or wrong — they&apos;re all forecasts.
                      </div>
                    </>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      Select a location and at least one model to see how much the forecasts
                      disagree.
                    </div>
                  )}
                </div>
              </div>

              {errorResults.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {errorResults.map((result) => (
                    <span
                      key={result.dataProduct.id}
                      className="text-xs px-2 py-0.5 rounded bg-destructive/10 text-destructive"
                    >
                      {modelLabel(result.dataProduct.id)}: {result.error || "unavailable"}
                    </span>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <Card>
                  <CardContent className="p-3 text-sm">
                    <div className="text-xs text-muted-foreground">Biggest disagreement</div>
                    {stats && stats.bigA && stats.bigB ? (
                      <>
                        {modelLabel(stats.bigA)} vs {modelLabel(stats.bigB)} at {stats.bigH ?? 0}h —{" "}
                        {stats.bigVal !== null ? stats.bigVal.toFixed(2) : "—"} {varMeta.unit}
                      </>
                    ) : (
                      "—"
                    )}
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-3 text-sm">
                    <div className="text-xs text-muted-foreground">Spread at 24h / 72h / 7d</div>
                    {spreadSummary}
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-3 text-sm">
                    <div className="text-xs text-muted-foreground">Run age</div>
                    {runAgeSummary}
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardContent className="p-3">
                  <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">
                      Time series
                    </div>
                    <div
                      className="flex items-center gap-1 border border-border rounded p-0.5"
                      role="tablist"
                      aria-label="Chart view"
                    >
                      {TAB_ORDER.map((entry, index) => (
                        <button
                          key={entry}
                          id={`tab-${entry}`}
                          type="button"
                          role="tab"
                          aria-selected={tab === entry}
                          aria-controls={`panel-${entry}`}
                          tabIndex={tab === entry ? 0 : -1}
                          onClick={() => setTab(entry)}
                          onKeyDown={(event) => onTabKeyDown(event, index)}
                          className={`text-xs px-2 py-1 rounded focus-visible:ring-2 focus-visible:ring-ring ${
                            tab === entry
                              ? "bg-primary text-primary-foreground"
                              : "hover:bg-accent/10"
                          }`}
                        >
                          {entry === "fan"
                            ? "Fan chart"
                            : entry === "spaghetti"
                              ? "Spaghetti"
                              : entry === "agreement"
                                ? "Agreement strip"
                                : "Table view"}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div
                    id={`panel-${tab}`}
                    role="tabpanel"
                    aria-labelledby={`tab-${tab}`}
                    tabIndex={0}
                    className="focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {tab === "fan" ? (
                      <ChartContainer
                        config={{}}
                        className="h-[360px] w-full"
                        role="img"
                        aria-label={`${varMeta.label} forecast fan chart`}
                      >
                        <ComposedChart data={chartData}>
                          <CartesianGrid vertical={false} />
                          <XAxis
                            dataKey="time"
                            tickLine={false}
                            axisLine={false}
                            tickMargin={8}
                            interval="preserveStartEnd"
                            minTickGap={40}
                          />
                          <YAxis
                            tickLine={false}
                            axisLine={false}
                            width={48}
                            tickFormatter={(value: number) =>
                              Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(1)
                            }
                          />
                          <Area
                            type="monotone"
                            dataKey={["_p90Low", "_p90High"] as unknown as string}
                            stroke="none"
                            fill="#4fd1c5"
                            fillOpacity={0.08}
                            isAnimationActive={false}
                          />
                          <Area
                            type="monotone"
                            dataKey={["_p50Low", "_p50High"] as unknown as string}
                            stroke="none"
                            fill="#4fd1c5"
                            fillOpacity={0.18}
                            isAnimationActive={false}
                          />
                          {results.map((result) => {
                            const id = result.dataProduct.id;
                            const model = MODELS.find((entry) => entry.id === id);
                            if (result._ensemble) {
                              return (
                                <Line
                                  key={id}
                                  type="monotone"
                                  dataKey={id}
                                  stroke={COLORS[id] || "#fff"}
                                  strokeWidth={2}
                                  strokeDasharray={model?.dash?.join(" ")}
                                  dot={false}
                                  isAnimationActive={false}
                                  connectNulls
                                />
                              );
                            }
                            return (
                              <Line
                                key={id}
                                type="monotone"
                                dataKey={id}
                                stroke={COLORS[id] || "#fff"}
                                strokeWidth={id === primaryModel ? 2.6 : 1.5}
                                strokeDasharray={model?.dash?.join(" ")}
                                dot={false}
                                isAnimationActive={false}
                                connectNulls
                              />
                            );
                          })}
                          <Line
                            type="monotone"
                            dataKey="_ensMedian"
                            stroke="#4fd1c5"
                            strokeWidth={2.5}
                            dot={false}
                            connectNulls
                            isAnimationActive={false}
                            name="Ensemble median"
                          />
                          {results
                            .filter((result) => result._ensemble)
                            .flatMap((result) => {
                              const id = result.dataProduct.id;
                              return [
                                <Line
                                  key={`${id}_min`}
                                  type="monotone"
                                  dataKey={`${id}_min`}
                                  stroke={COLORS[id] || "#fff"}
                                  strokeWidth={0}
                                  dot={false}
                                  isAnimationActive={false}
                                />,
                                <Line
                                  key={`${id}_max`}
                                  type="monotone"
                                  dataKey={`${id}_max`}
                                  stroke={COLORS[id] || "#fff"}
                                  strokeWidth={0}
                                  dot={false}
                                  isAnimationActive={false}
                                />,
                              ];
                            })}
                        </ComposedChart>
                      </ChartContainer>
                    ) : tab === "spaghetti" ? (
                      <ChartContainer
                        config={{}}
                        className="h-[360px] w-full"
                        role="img"
                        aria-label={`${varMeta.label} ensemble spaghetti chart`}
                      >
                        <ComposedChart data={chartData}>
                          <CartesianGrid vertical={false} />
                          <XAxis
                            dataKey="time"
                            tickLine={false}
                            axisLine={false}
                            tickMargin={8}
                            interval="preserveStartEnd"
                            minTickGap={40}
                          />
                          <YAxis
                            tickLine={false}
                            axisLine={false}
                            width={48}
                            tickFormatter={(value: number) => value.toFixed(1)}
                          />
                          {results.map((result) => {
                            const id = result.dataProduct.id;
                            if (result._ensemble) {
                              return (result._ensemble || []).map((member, memberIndex) => (
                                <Line
                                  key={`${id}_m${memberIndex}`}
                                  type="monotone"
                                  dataKey={`${id}_m${memberIndex}`}
                                  stroke={COLORS[id] || "#fff"}
                                  strokeOpacity={0.18}
                                  strokeWidth={1}
                                  dot={false}
                                  isAnimationActive={false}
                                  legendType="none"
                                />
                              ));
                            }
                            return (
                              <Line
                                key={id}
                                type="monotone"
                                dataKey={id}
                                stroke={COLORS[id] || "#fff"}
                                strokeWidth={1.8}
                                dot={false}
                                isAnimationActive={false}
                              />
                            );
                          })}
                          {results.some((result) => result._ensemble) && (
                            <Line
                              type="monotone"
                              dataKey="_ensMedian"
                              stroke="#4fd1c5"
                              strokeWidth={2.5}
                              dot={false}
                              connectNulls
                              isAnimationActive={false}
                              name="Ensemble median"
                            />
                          )}
                        </ComposedChart>
                      </ChartContainer>
                    ) : tab === "agreement" ? (
                      <div className="overflow-auto">
                        <div
                          className="grid text-xs"
                          style={{
                            gridTemplateColumns: `120px repeat(${Math.ceil((stats?.leads.length || 0) / 6)}, 1fr)`,
                          }}
                        >
                          <div />
                          {(stats?.leads || [])
                            .filter((_, index) => index % 6 === 0)
                            .map((time) => (
                              <div
                                key={time}
                                className="text-center text-muted-foreground font-mono"
                              >
                                {time.slice(0, 10)} {time.slice(11, 16)}
                              </div>
                            ))}
                          {results
                            .filter((result) => (result._times || []).length)
                            .map((result) => (
                              <Fragment key={result.dataProduct.id}>
                                <div className="truncate">{modelLabel(result.dataProduct.id)}</div>
                                {(stats?.leads || [])
                                  .filter((_, index) => index % 6 === 0)
                                  .map((time) => {
                                    const value = valueAtTime(result, variable, time);
                                    const median = stats?.multiMedian?.[stats.leads.indexOf(time)];
                                    const deviation =
                                      typeof value === "number" && typeof median === "number"
                                        ? Math.abs(value - median)
                                        : 0;
                                    const ratio = Math.min(1, deviation / varMeta.scale);
                                    const light = 30 + ratio * 40;
                                    return (
                                      <div
                                        key={`${result.dataProduct.id}-${time}`}
                                        style={{
                                          background: `hsl(${Math.round(30 + (1 - ratio) * 30)},70%,${light}%)`,
                                          height: 18,
                                          borderRadius: 2,
                                        }}
                                        title={`${modelLabel(result.dataProduct.id)} ${time.slice(11, 16)}: ${
                                          typeof value === "number" ? value.toFixed(2) : "—"
                                        }`}
                                      />
                                    );
                                  })}
                              </Fragment>
                            ))}
                        </div>
                      </div>
                    ) : (
                      <div className="overflow-auto max-h-[60vh]">
                        <table className="w-full text-xs">
                          <thead className="sticky top-0 bg-card">
                            <tr className="text-left text-muted-foreground">
                              <th className="py-1 pr-2 font-medium">Time</th>
                              {results.map((result) => (
                                <th key={result.dataProduct.id} className="py-1 px-2 font-medium">
                                  {modelLabel(result.dataProduct.id)}
                                </th>
                              ))}
                              <th className="py-1 px-2 font-medium">Median</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(stats?.leads || []).map((time, index) => {
                              const median = stats?.multiMedian?.[index] ?? null;
                              return (
                                <tr key={time} className="border-t border-border/60">
                                  <td className="py-1 pr-2 font-mono">
                                    {time.slice(0, 16).replace("T", " ")}
                                  </td>
                                  {results.map((result) => {
                                    const value = valueAtTime(result, variable, time);
                                    return (
                                      <td
                                        key={result.dataProduct.id}
                                        className="py-1 px-2 tabular-nums"
                                      >
                                        {typeof value === "number" ? value.toFixed(2) : "—"}
                                      </td>
                                    );
                                  })}
                                  <td className="py-1 px-2 tabular-nums font-medium">
                                    {typeof median === "number" ? median.toFixed(2) : "—"}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {tab === "fan" && (
                    <div className="text-xs text-muted-foreground mt-2">
                      Fan chart: median line, 50% and 90% ensemble bands. Wider band = less
                      agreement.
                    </div>
                  )}
                </CardContent>
              </Card>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-2 items-center">
            <Button variant="secondary" size="sm" onClick={downloadCsv}>
              Download CSV
            </Button>
            <Button variant="secondary" size="sm" onClick={copyJson}>
              Copy as JSON
            </Button>
            <Button variant="secondary" size="sm" onClick={copyLink}>
              Copy shareable link
            </Button>
            {copyStatus && (
              <span className="text-xs text-muted-foreground" role="status">
                {copyStatus}
              </span>
            )}
          </div>

          {!loading && !data && !error && (
            <div className="text-sm text-muted-foreground" role="status">
              Select a location and at least one model to see a forecast.
            </div>
          )}
          {!loading && data && results.length === 0 && (
            <div className="text-sm text-muted-foreground" role="status">
              No model data returned. Try another location, run, or model.
            </div>
          )}
        </main>
      </div>

      <footer className="border-t border-border mt-6">
        <div className="max-w-7xl mx-auto px-4 py-4 text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
          <span>
            Data: NOAA GFS/HRRR/GEFS, ECMWF AIFS/IFS ENS, DWD ICON-EU via{" "}
            <a
              href="https://dynamical.org/catalog"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Dynamical
            </a>
            .
          </span>
          <span>Licenses vary by model; see the catalog.</span>
          <Link href="/map" className="underline">
            Map view
          </Link>
          <button
            type="button"
            className="underline focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setShowHowTo(true)}
          >
            Attribution &amp; method
          </button>
        </div>
      </footer>

      {showHowTo && (
        <div
          className="fixed inset-0 z-50 bg-black/60 p-4 grid place-items-center"
          onClick={closeModal}
        >
          <div
            ref={modalRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="howto-title"
            className="max-w-lg w-full"
            onClick={(event) => event.stopPropagation()}
          >
            <Card>
              <CardContent className="p-5 space-y-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <h2 id="howto-title" className="text-base font-semibold">
                    How to read this
                  </h2>
                  <Button variant="ghost" size="sm" onClick={closeModal}>
                    Close
                  </Button>
                </div>
                <div>
                  <strong>What a fan chart is</strong>
                  <p className="text-muted-foreground">
                    An ensemble forecast shown as a median line with shaded 50% and 90% bands. Wider
                    fan = less self-agreement.
                  </p>
                </div>
                <div>
                  <strong>What &quot;agreement&quot; means</strong>
                  <p className="text-muted-foreground">
                    Two measures: ensemble spread and inter-model deviation. Both must be small for
                    high confidence.
                  </p>
                </div>
                <div>
                  <strong>What it is not</strong>
                  <p className="text-muted-foreground">
                    It is not a probability of rain or a guarantee. It is a measure of how much the
                    models disagree with each other. Every model can be wrong in the same direction.
                  </p>
                </div>
                <div className="text-xs text-muted-foreground border-t border-border pt-2">
                  Data: NOAA GFS/HRRR/GEFS, ECMWF AIFS/IFS ENS, DWD ICON-EU via{" "}
                  <a
                    href="https://dynamical.org/catalog"
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    Dynamical
                  </a>
                  . Model licenses and attribution are listed in the catalog. Forecast data is for
                  exploration, not safety-critical decisions.
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
