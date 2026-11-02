/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable react/no-unescaped-entities */
/* eslint-disable react-hooks/set-state-in-effect */
"use client";

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Line, LineChart, Area, XAxis, YAxis, CartesianGrid, Legend } from "recharts";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const MODELS = [
  { id: "noaa-gfs-forecast", label: "NOAA GFS", type: "Deterministic", horizon: 384, color: "#60a5fa", dash: [], desc: "Global, 0.25°, hourly updates." },
  { id: "noaa-hrrr-forecast-48-hour", label: "NOAA HRRR", type: "Deterministic", horizon: 48, color: "#34d399", dash: [], desc: "3km convection-allowing, US only." },
  { id: "ecmwf-aifs-single-forecast", label: "ECMWF AIFS", type: "Deterministic", horizon: 360, color: "#a78bfa", dash: [6, 4], desc: "ECMWF machine-learning model." },
  { id: "dwd-icon-eu-forecast-5-day", label: "DWD ICON-EU", type: "Deterministic", horizon: 120, color: "#fbbf24", dash: [2, 4], desc: "High-res Europe." },
  { id: "noaa-gefs-forecast-35-day", label: "NOAA GEFS", type: "Ensemble", horizon: 840, color: "#f472b6", dash: [], desc: "31 members, 35-day horizon.", members: 31 },
  { id: "ecmwf-ifs-ens-forecast-15-day-0-25-degree", label: "ECMWF IFS ENS", type: "Ensemble", horizon: 360, color: "#22d3ee", dash: [], desc: "50 members, 15-day horizon.", members: 50 },
  { id: "noaa-gfs-analysis", label: "NOAA GFS analysis", type: "Analysis", horizon: 0, color: "#94a3b8", dash: [1, 3], desc: "What actually happened (GFS)." },
  { id: "noaa-hrrr-analysis", label: "NOAA HRRR analysis", type: "Analysis", horizon: 0, color: "#cbd5e1", dash: [1, 3], desc: "What actually happened (HRRR)." },
];

const VARS = [
  { id: "temperature_2m", label: "Temperature", unit: "°C", scale: 10 },
  { id: "relative_humidity_2m", label: "Humidity", unit: "%", scale: 20 },
  { id: "precipitation_surface", label: "Precipitation", unit: "mm", scale: 5 },
  { id: "total_cloud_cover_atmosphere", label: "Cloud cover", unit: "%", scale: 30 },
  { id: "downward_short_wave_radiation_flux_surface", label: "Solar radiation", unit: "W/m²", scale: 200 },
  { id: "pressure_reduced_to_mean_sea_level", label: "Pressure", unit: "hPa", scale: 10 },
  { id: "wind_u_10m", label: "Wind U", unit: "m/s", scale: 8 },
  { id: "wind_v_10m", label: "Wind V", unit: "m/s", scale: 8 },
  { id: "wind_speed", label: "Wind speed", unit: "m/s", scale: 8 },
];

const COLORS = ["#60a5fa", "#34d399", "#f87171", "#fbbf24", "#a78bfa", "#22d3ee", "#f472b6", "#94a3b8"];

function median(a: number[]) {
  const s = [...a].sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function percentile(a: number[], p: number) {
  const s = [...a].sort((x, y) => x - y);
  const idx = (s.length - 1) * p;
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return s[lo];
  return s[lo] + (s[hi] - s[lo]) * (idx - lo);
}
function std(a: number[]) {
  const m = a.reduce((x, y) => x + y, 0) / a.length;
  return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / a.length);
}

export default function Home() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [q, setQ] = useState("");
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [lat, setLat] = useState("41.88");
  const [lon, setLon] = useState("-87.63");
  const [variable, setVariable] = useState("temperature_2m");
  const [models, setModels] = useState<string[]>(["noaa-gfs-forecast", "noaa-hrrr-forecast-48-hour", "noaa-gefs-forecast-35-day", "noaa-gfs-analysis"]);
  const [maxLead, setMaxLead] = useState(48);
  const [snapshot, setSnapshot] = useState("latest");
  const [runOptions, setRunOptions] = useState<string[]>(["latest"]);
  const [latestInitTime, setLatestInitTime] = useState<string | null>(null);
  const [tab, setTab] = useState<"fan" | "spaghetti" | "agreement" | "table">("fan");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [showHowTo, setShowHowTo] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const varMeta = VARS.find((v) => v.id === variable) || VARS[0];
  const modelLabel = (id: string) => MODELS.find((m) => m.id === id)?.label || id;
  function modelValueAt(r: any, v: string, idx: number) {
    if (isEnsemble(r)) {
      const arr = (r._ensemble || []).map((m: any) => m.data?.[v]?.[idx]).filter((x: any) => typeof x === "number");
      return arr.length ? median(arr) : null;
    }
    return (r._data || {})[v]?.[idx] ?? null;
  }
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    if (q.trim().length < 2) { setSuggestions([]); return; }
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`${API}/api/geocode?q=${encodeURIComponent(q)}`);
        const d = await res.json();
        setSuggestions(d.results || []);
      } catch { setSuggestions([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  // URL state
  useEffect(() => {
    if (models.length === 0) return;
    fetch(`${API}/api/runs?dataProductId=${models[0]}&limit=5`)
      .then((r) => r.json())
      .then((d) => {
        const opts = (d.runs || []).map((x: any) => x.initTime);
        if (opts.length) { setRunOptions(["latest", ...opts]); setLatestInitTime(opts[0]); }
      })
      .catch(() => {});
  }, [models]);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    if (p.has("lat")) setLat(p.get("lat")!);
    if (p.has("lon")) setLon(p.get("lon")!);
    if (p.has("v")) setVariable(p.get("v")!);
    if (p.has("models")) setModels(p.get("models")!.split(",").filter(Boolean));
    if (p.has("lead")) setMaxLead(Number(p.get("lead")));
    if (p.has("snap")) setSnapshot(p.get("snap")!);
    if (p.has("theme")) setTheme(p.get("theme") as any);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("lat", lat); params.set("lon", lon); params.set("v", variable);
    params.set("models", models.join(",")); params.set("lead", String(maxLead));
    params.set("snap", snapshot); params.set("theme", theme);
    window.history.replaceState(null, "", "?" + params.toString());
  }, [lat, lon, variable, models, maxLead, snapshot, theme]);

  function toggleModel(id: string) {
    setModels((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function fetchForecast(ctrl?: AbortController) {
    if (models.length === 0) { setError("Select at least one model."); return; }
    setError(null);
    try {
      const fetchVars = variable === "wind_speed" ? ["wind_u_10m", "wind_v_10m"] : [variable];
      const forecastModels = models.filter((m) => !m.includes("analysis"));
      const analysisModels = models.filter((m) => m.includes("analysis"));
      const allResults: any[] = [];
      if (forecastModels.length) {
        const res = await fetch(`${API}/api/point`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ latitude: Number(lat), longitude: Number(lon), products: forecastModels, variables: fetchVars, maxLeadTimeHours: maxLead, initTime: snapshot === "latest" ? "latest" : snapshot }),
          signal: ctrl?.signal,
        });
        if (!res.ok) throw new Error(await res.text());
        const json = await res.json();
        allResults.push(...(json.results || []));
      }
      if (analysisModels.length) {
        const init = snapshot === "latest" ? (latestInitTime || new Date().toISOString()) : snapshot;
        const initDate = new Date(init);
        const endMs = Math.min(Date.now(), initDate.getTime() + maxLead * 3600 * 1000);
        const res = await fetch(`${API}/api/analysis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ latitude: Number(lat), longitude: Number(lon), products: analysisModels, variables: fetchVars, startTime: initDate.toISOString(), endTime: new Date(endMs).toISOString() }),
          signal: ctrl?.signal,
        });
        if (!res.ok) throw new Error(await res.text());
        const json = await res.json();
        allResults.push(...(json.results || []));
      }
      allResults.forEach((r: any) => {
        if (r.status && r.status !== "ok") return;
        if (r.forecasts?.[0]) {
          r._times = r.forecasts[0].validTimes || [];
          r._data = r.forecasts[0].data || {};
          r._ensemble = r.forecasts[0].ensembleMembers || null;
        } else {
          r._times = r.analysisTimes || [];
          r._data = r.data || {};
          r._ensemble = null;
        }
        if (variable === "wind_speed") {
          const u = r._data["wind_u_10m"] || [];
          const v = r._data["wind_v_10m"] || [];
          r._data["wind_speed"] = u.map((val: number, i: number) => (typeof val === "number" && typeof v[i] === "number") ? Math.sqrt(val * val + v[i] * v[i]) : null);
        }
        if (variable === "wind_speed" && Array.isArray(r._ensemble)) {
          r._ensemble.forEach((m: any) => {
            const u = m.data?.wind_u_10m || [];
            const v = m.data?.wind_v_10m || [];
            m.data = m.data || {};
            m.data.wind_speed = u.map((val: number, i: number) => (typeof val === "number" && typeof v[i] === "number") ? Math.sqrt(val * val + v[i] * v[i]) : null);
          });
        }

      });
      setData({ results: allResults });
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      setError(e.message);
    }

  }

  useEffect(() => {
    const keep = (id: string) => {
      const m = MODELS.find((x) => x.id === id);
      return !m || m.type === "Analysis" || m.horizon >= maxLead;
    };
    const dropped = models.filter((id) => !keep(id)).map((id) => MODELS.find((x) => x.id === id)?.label || id);
    if (dropped.length) {
      setModels((prev) => prev.filter(keep));
      setNotice(`${dropped.join(", ")} dropped: horizon shorter than ${maxLead}h.`);
    } else {
      setNotice(null);
    }
  }, [maxLead, models]);

  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current?.abort();
    abortRef.current = ctrl;
    const t = setTimeout(() => {
      fetchForecast(ctrl);
    }, 400);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [lat, lon, variable, models, maxLead, snapshot, latestInitTime]); // eslint-disable-line react-hooks/exhaustive-deps

  function useMyLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      setLat(pos.coords.latitude.toFixed(4));
      setLon(pos.coords.longitude.toFixed(4));
    });
  }

  const results = (data?.results || []).filter((r: any) => !r.status || r.status === "ok");

  function buildChartData() {
    const tsSet = new Set<string>();
    results.forEach((r: any) => (r._times || []).forEach((t: string) => tsSet.add(t)));
    const sorted = [...tsSet].sort();
    // ensemble bands aligned by lead index
    const ensModels = results.filter(isEnsemble);
    const allMembers = ensModels.flatMap((r: any) => r._ensemble || []);
    return sorted.map((t, idx) => {
      const row: any = { time: t.slice(5, 16).replace("T", " ") };
      const vals = allMembers.map((m: any) => {
        if (variable === "wind_speed") {
          const u = m.data?.wind_u_10m?.[idx]; const v = m.data?.wind_v_10m?.[idx];
          return (typeof u === "number" && typeof v === "number") ? Math.sqrt(u * u + v * v) : null;
        }
        return m.data?.[variable]?.[idx] ?? null;
      }).filter((v: any) => typeof v === "number");
      if (vals.length) {
        row._ensMedian = median(vals);
        row._p50Low = percentile(vals, 0.25);
        row._p50High = percentile(vals, 0.75);
        row._p90Low = percentile(vals, 0.05);
        row._p90High = percentile(vals, 0.95);
      }
      results.forEach((r: any) => {
        const idx = (r._times || []).indexOf(t);
        if (idx < 0) return;
        const id = r.dataProduct.id;
        if (Array.isArray(r._ensemble)) {
          const vals = r._ensemble.map((m: any) => m.data?.[variable === "wind_speed" ? "wind_u_10m" : variable]?.[idx]).filter((v: any) => typeof v === "number");
          // for wind speed use u/v
          if (variable === "wind_speed") {
            const us = r._ensemble.map((m: any) => m.data?.wind_u_10m?.[idx]);
            const vs = r._ensemble.map((m: any) => m.data?.wind_v_10m?.[idx]);
            const speeds = us.map((u: any, i: number) => (typeof u === "number" && typeof vs[i] === "number") ? Math.sqrt(u * u + vs[i] * vs[i]) : null).filter((v: any) => v !== null);
            if (speeds.length) {
              row[id] = speeds.reduce((a: number, b: number) => a + b, 0) / speeds.length;
              row[`${id}_min`] = Math.min(...speeds);
              row[`${id}_max`] = Math.max(...speeds);
            }
          } else if (vals.length) {
            row[id] = vals.reduce((a: number, b: number) => a + b, 0) / vals.length;
            const all = r._ensemble.map((m: any) => m.data?.[variable]?.[idx]).filter((v: any) => typeof v === "number");
            row[`${id}_min`] = Math.min(...all);
            row[`${id}_max`] = Math.max(...all);
          }
          // member keys for spaghetti
          (r._ensemble || []).forEach((m: any, mi: number) => {
            if (variable === "wind_speed") {
              const u = m.data?.wind_u_10m?.[idx]; const v = m.data?.wind_v_10m?.[idx];
              row[`${id}_m${mi}`] = (typeof u === "number" && typeof v === "number") ? Math.sqrt(u * u + v * v) : null;
            } else {
              row[`${id}_m${mi}`] = m.data?.[variable]?.[idx] ?? null;
            }
          });
        } else {
          row[id] = (r._data || {})[variable]?.[idx] ?? null;
        }
      });
      return row;
    });
  }

  function isEnsemble(r: any) { return Array.isArray(r._ensemble); }

  // computations for confidence/headline/cards
  function computeStats() {
    if (!results.length) return null;
    const tsSet = new Set<string>();
    results.forEach((r: any) => (r._times || []).forEach((t: string) => tsSet.add(t)));
    const leads = [...tsSet].sort();
    const modelValue = (r: any, idx: number) => {
      if (isEnsemble(r)) {
        const arr = (r._ensemble || []).map((m: any) => m.data?.[variable]?.[idx]).filter((x: any) => typeof x === "number");
        return arr.length ? median(arr) : null;
      }
      return (r._data || {})[variable]?.[idx] ?? null;
    };
    const modelPoints = leads.map((t) =>
      results.map((r: any) => {
        const idx = (r._times || []).indexOf(t);
        if (idx < 0) return null;
        const v = modelValue(r, idx);
        return typeof v === "number" ? v : null;
      }).filter((v: any) => v !== null)
    );
    const ensModels = results.filter(isEnsemble);
    const allMembers: number[][] = [];
    ensModels.forEach((r: any) => (r._ensemble || []).forEach((m: any) => {
      const arr = leads.map((t) => {
        const idx = (r._times || []).indexOf(t);
        if (idx < 0) return null;
        if (variable === "wind_speed") {
          const u = m.data?.wind_u_10m?.[idx]; const v = m.data?.wind_v_10m?.[idx];
          return (typeof u === "number" && typeof v === "number") ? Math.sqrt(u * u + v * v) : null;
        }
        return m.data?.[variable]?.[idx] ?? null;
      });
      allMembers.push(arr);
    }));
    const ensMedian = leads.map((_, i) => {
      const vals = allMembers.map((m) => m[i]).filter((v: any) => typeof v === "number");
      return vals.length ? median(vals) : null;
    });
    const spread = leads.map((_, i) => {
      const vals = allMembers.map((m) => m[i]).filter((v: any) => typeof v === "number");
      return vals.length > 1 ? std(vals) : 0;
    });
    const multiVals = leads.map((_, i) => [...modelPoints[i], ...(ensMedian[i] !== null ? [ensMedian[i]!] : [])]);
    const multiMedian = multiVals.map((vals) => (vals.length ? median(vals) : null));
    const interdev = multiVals.map((vals) => (vals.length > 1 ? std(vals) : 0));
    const thr = varMeta.scale * 0.3;
    let agreeUntil = leads.length - 1;
    for (let i = 0; i < leads.length; i++) {
      if ((spread[i] || 0) > thr || (interdev[i] || 0) > thr) { agreeUntil = i; break; }
    }
    const maxSplit = Math.max(0, ...leads.map((_, i) => {
      const vals = multiVals[i]; if (!vals.length) return 0;
      return Math.max(...vals) - Math.min(...vals);
    }));
    const idx24 = Math.min(24, leads.length - 1);
    const idx72 = Math.min(72, leads.length - 1);
    const idx7d = Math.min(168, leads.length - 1);
    const avgSpread = [spread[idx24], spread[idx72], spread[idx7d]].filter((v: any) => typeof v === "number");
    const avgInter = [interdev[idx24], interdev[idx72], interdev[idx7d]].filter((v: any) => typeof v === "number");
    const ns = Math.min(1, (avgSpread.reduce((a, b) => a + b, 0) / (avgSpread.length || 1)) / varMeta.scale);
    const ni = Math.min(1, (avgInter.reduce((a, b) => a + b, 0) / (avgInter.length || 1)) / varMeta.scale);
    const score = Math.round(100 * (1 - (ns + ni) / 2));
    const label = score >= 70 ? "High" : score >= 40 ? "Medium" : "Low";
    let bigIdx = 0, bigVal = 0, bigA = "", bigB = "";
    leads.forEach((t, i) => {
      const pts = results.map((r: any) => {
        const idx = (r._times || []).indexOf(t);
        if (idx < 0) return null;
        const v = modelValue(r, idx);
        return typeof v === "number" ? { id: r.dataProduct.id, v } : null;
      }).filter((x: any) => x !== null);
      if (pts.length < 2) return;
      pts.sort((a: any, b: any) => a.v - b.v);
      const diff = pts[pts.length - 1].v - pts[0].v;
      if (diff > bigVal) { bigVal = diff; bigIdx = i; bigA = pts[0].id; bigB = pts[pts.length - 1].id; }
    });
    const spreadAt = (target: number) => {
      const i = leads.findIndex((t) => {
        const h = Number(t.match(/T(\d{2}):/)?.[1] || 0);
        return false;
      });
      return (spread[Math.min(target, leads.length - 1)] || 0).toFixed(2);
    };
    return { leads, spread, multiMedian, interdev, score, label, thr, agreeUntil, maxSplit, bigH: bigIdx, bigVal, bigA, bigB, spreadAt, runAge: results.map((r: any) => r.forecasts?.[0]?.initTime || r.analysisTimes?.[0] || "n/a").join(", "), ensMedian };
  }

  const stats = data ? computeStats() : null;
  const chartData = data ? buildChartData() : [];

  function exportCsv() {
    if (!data) return;
    const tsSet = new Set<string>();
    results.forEach((r: any) => (r._times || []).forEach((t: string) => tsSet.add(t)));
    const sorted = [...tsSet].sort();
    const header = ["timestamp", ...results.map((r: any) => r.dataProduct.id)].join(",");
    const lines = sorted.map((t) => {
      const vals = results.map((r: any) => {
        const idx = (r._times || []).indexOf(t);
        if (idx < 0) return "";
        if (isEnsemble(r)) {
          const arr = r._ensemble.map((m: any) => {
            if (variable === "wind_speed") {
              const u = m.data?.wind_u_10m?.[idx]; const v = m.data?.wind_v_10m?.[idx];
              return (typeof u === "number" && typeof v === "number") ? Math.sqrt(u * u + v * v) : null;
            }
            return m.data?.[variable]?.[idx];
          }).filter((x: any) => typeof x === "number");
          return arr.length ? (arr.reduce((a: number, b: number) => a + b, 0) / arr.length).toFixed(3) : "";
        }
        return (r._data || {})[variable]?.[idx] ?? "";
      });
      return [t, ...vals].join(",");
    });
    const csv = [header, ...lines].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "forecast.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  function copyJson() {
    if (!data) return;
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
  }

  function copyLink() {
    navigator.clipboard.writeText(window.location.href);
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="flex items-center justify-between border-b border-border px-4 py-3 bg-card">
        <div>
          <div className="font-bold tracking-tight">Disagreement</div>
          <div className="text-xs text-muted-foreground">Weather isn't a number. It's a disagreement.</div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setShowHowTo(true)}>How to read this</Button>
          <Button variant="ghost" size="sm" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            {theme === "dark" ? "Light" : "Dark"}
          </Button>
        </div>
      </header>

      <div className="flex">
        {/* Left rail */}
        <aside className="w-72 shrink-0 border-r border-border bg-card p-4 md:block">
          <div className="space-y-4">
            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase mb-1">Location</div>
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search city…" className="mb-2" />
              {suggestions.length > 0 && (
                <div className="border border-border rounded-md max-h-40 overflow-auto mb-2">
                  {suggestions.map((s) => (
                    <button key={s.id} className="block w-full text-left px-2 py-1 text-sm hover:bg-accent/10" onClick={() => { setLat(String(s.latitude)); setLon(String(s.longitude)); setQ(s.name); setSuggestions([]); }}>
                      {s.name}
                    </button>
                  ))}
                </div>
              )}
              <Button variant="secondary" size="sm" onClick={useMyLocation} className="w-full mb-1">Use my location</Button>
              <div className="font-mono text-xs text-muted-foreground">{lat}, {lon}</div>
            </div>

            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase mb-1">Variable</div>
              <div className="grid grid-cols-2 gap-1">
                {VARS.map((v) => (
                  <button key={v.id} className={`text-xs px-2 py-1 rounded border ${variable === v.id ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-accent/10"}`} onClick={() => setVariable(v.id)}>
                    {v.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase mb-1">Models</div>
              {["Deterministic", "Ensemble", "Analysis"].map((grp) => (
                <div key={grp} className="mb-2">
                  <div className="text-xs text-muted-foreground mb-1">{grp}</div>
                  {MODELS.filter((m) => m.type === grp).map((m) => {
                    const avail = m.type === "Analysis" || m.horizon >= maxLead;
                    return (
                      <label key={m.id} className={`flex items-start gap-2 text-xs mb-1 ${avail ? "" : "opacity-40"}`} title={avail ? "" : `${m.label} does not reach ${maxLead}h`}>
                        <Checkbox checked={models.includes(m.id)} disabled={!avail} onCheckedChange={() => avail && toggleModel(m.id)} />
                        <span className="inline-block w-4 h-0.5 mt-1.5" style={{ background: m.color, borderTop: m.dash.length ? `2px dashed ${m.color}` : `2px solid ${m.color}` }} />
                        <span>
                          <span className="font-medium">{m.label}</span>
                          <span className="block text-muted-foreground">{m.desc} · {m.type === "Analysis" ? "analysis" : m.horizon + "h"}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>

            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase mb-1">Lead time (h)</div>
              <input type="range" min={6} max={840} step={6} value={maxLead} onChange={(e) => setMaxLead(Number(e.target.value))} className="w-full" />
              <div className="flex flex-wrap gap-1 mt-1">
                {[6, 24, 48, 168, 384, 840].map((p) => (
                  <Button key={p} size="sm" variant="secondary" onClick={() => setMaxLead(p)}>{p < 24 ? p + "h" : p < 168 ? Math.round(p / 24) + "d" : p === 168 ? "7d" : p === 384 ? "16d" : "35d"}</Button>
                ))}
              </div>
              <div className="text-xs text-muted-foreground mt-1">0 → {maxLead}h</div>
            </div>

            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase mb-1">Snapshot</div>
              <select className="w-full border border-border rounded px-2 py-1 bg-background text-sm" value={snapshot} onChange={(e) => setSnapshot(e.target.value)}>
                <option value="latest">Latest run</option>
                {runOptions.filter((r) => r !== "latest").map((rt) => (
                  <option key={rt} value={rt}>{rt}</option>
                ))}
              </select>

            </div>

            {error && <div className="text-xs text-destructive">{error}</div>}
          </div>
        </aside>

        {/* Main panel */}
        <main className="flex-1 p-4 space-y-4">
          <div>
            <div className="text-lg font-semibold">{stats ? `Models agree within ${(varMeta.scale * 0.3).toFixed(1)}${varMeta.unit} through ${stats.agreeUntil < 24 ? "the next " + stats.agreeUntil + "h" : Math.round(stats.agreeUntil / 24) + "d"}, then split by up to ${stats.maxSplit.toFixed(1)}${varMeta.unit}.` : "Waiting on the models…"}</div>
            <div className="flex items-center gap-3 mt-2">
              <span className="text-sm">{stats ? stats.label + " confidence" : "—"}</span>
              <div className="flex-1 h-2 bg-muted rounded overflow-hidden">
                <div className="h-full bg-primary transition-all" style={{ width: (stats?.score || 0) + "%" }} />
              </div>
              <span className="font-mono text-sm">{stats ? stats.score + "/100" : "—"}</span>
            </div>
            <div className="text-xs text-muted-foreground mt-1">Rule: 100 × (1 − (normalized ensemble spread + normalized inter-model deviation)/2).</div>
            {notice && <div className="text-xs text-amber-400 mt-1">{notice}</div>}
          </div>

          {data?.results?.some((r: any) => r.status === "error") && (
            <div className="flex flex-wrap gap-2">
              {(data.results || []).filter((r: any) => r.status === "error").map((r: any) => (
                <Badge key={r.product} variant="destructive" className="text-xs">
                  {modelLabel(r.dataProduct?.id || r.product)}: {r.error?.slice(0, 80) || "failed"}
                </Badge>
              ))}
            </div>
          )}

          <div className="flex gap-1 border-b border-border">
            {(["fan", "spaghetti", "agreement", "table"] as const).map((t) => (
              <button key={t} className={`px-3 py-1.5 text-sm border-b-2 ${tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground"}`} onClick={() => setTab(t)}>
                {t === "fan" ? "Fan chart" : t === "spaghetti" ? "Spaghetti" : t === "agreement" ? "Agreement strip" : "Table view"}
              </button>
            ))}
          </div>

          <Card>
            <CardContent className="p-3">
              {tab === "agreement" ? (
                <div className="overflow-auto">
                  <div className="grid text-xs" style={{ gridTemplateColumns: `120px repeat(${Math.ceil((stats?.leads.length || 0) / 6)}, 1fr)` }}>
                    <div />
                    {(stats?.leads || []).filter((_: any, i: number) => i % 6 === 0).map((t: string) => (
                      <div key={t} className="text-center text-muted-foreground font-mono">{t.slice(11,16)}</div>
                    ))}
                    {results.filter((r: any) => (r._times || []).length).map((r: any) => (
                      <>
                        <div key={r.dataProduct.id + "-name"} className="truncate">{modelLabel(r.dataProduct.id)}</div>
                        {(stats?.leads || []).filter((_: any, i: number) => i % 6 === 0).map((t: string) => {
                          const idx = (r._times || []).indexOf(t);
                          const v = idx >= 0 ? modelValueAt(r, variable, idx) : null;
                          const med = stats?.multiMedian?.[stats.leads.indexOf(t)];
                          const dev = (typeof v === "number" && typeof med === "number") ? Math.abs(v - med) : 0;
                          const tt = Math.min(1, dev / varMeta.scale);
                          const light = 30 + tt * 40;
                          return <div key={r.dataProduct.id + "-" + t} style={{ background: `hsl(${Math.round(30 + (1 - tt) * 30)},70%,${light}%)`, height: 18, borderRadius: 2 }} title={`${modelLabel(r.dataProduct.id)} ${t.slice(11,16)}: ${typeof v === "number" ? v.toFixed(2) : "—"}`} />;
                        })}
                      </>
                    ))}
                  </div>
                </div>
              ) : tab === "table" ? (
                <div className="overflow-auto max-h-[60vh]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr>
                        <th className="text-left p-1">Lead</th>
                        {results.map((r: any) => <th key={r.dataProduct.id} className="text-left p-1">{r.dataProduct.id}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {(stats?.leads || []).map((t: string) => (
                        <tr key={t} className="border-t border-border">
                          <td className="p-1 font-mono">{t.slice(11,16)}</td>
                          {results.map((r: any) => {
                            const idx = (r._times || []).indexOf(t);
                            const v = idx >= 0 ? modelValueAt(r, variable, idx) : null;
                            return <td key={r.dataProduct.id} className="p-1 font-mono">{typeof v === "number" ? v.toFixed(2) : "—"}</td>;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="h-[60vh] min-h-[360px]">
                  <ChartContainer config={{}} className="h-full">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="time" fontSize={10} />
                      <YAxis fontSize={10} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Legend />
                      {tab === "fan" && chartData.some((d: any) => d._p90High != null) && (
                        <>
                          <Area type="monotone" dataKey={["_p90Low", "_p90High"] as any} stroke="none" fill="#4fd1c5" fillOpacity={0.08} name="90% band" />
                          <Area type="monotone" dataKey={["_p50Low", "_p50High"] as any} stroke="none" fill="#4fd1c5" fillOpacity={0.18} name="50% band" />
                          <Line type="monotone" dataKey="_ensMedian" stroke="#4fd1c5" strokeWidth={2.5} dot={false} connectNulls name="Ensemble median" />
                        </>
                      )}
                      {results.map((r: any) => (
                        <Line key={r.dataProduct.id} type="monotone" dataKey={r.dataProduct.id} stroke={MODELS.find((m) => m.id === r.dataProduct.id)?.color || COLORS[0]} strokeWidth={2} dot={false} connectNulls strokeDasharray={MODELS.find((m) => m.id === r.dataProduct.id)?.dash.join(" ")} name={modelLabel(r.dataProduct.id)} />
                      ))}
                      {tab === "spaghetti" && results.filter(isEnsemble).map((r: any) =>
                        (r._ensemble || []).map((_: any, mi: number) => (
                          <Line key={`${r.dataProduct.id}_m${mi}`} type="monotone" dataKey={`${r.dataProduct.id}_m${mi}`} stroke={MODELS.find((m) => m.id === r.dataProduct.id)?.color || "#999"} strokeWidth={0.8} strokeOpacity={0.25} dot={false} connectNulls legendType="none" />
                        ))
                      )}
                    </LineChart>
                  </ChartContainer>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <Card><CardContent className="p-3 text-sm"><div className="text-xs text-muted-foreground">Biggest disagreement</div>{stats ? `${modelLabel(stats.bigA)} vs ${modelLabel(stats.bigB)} at ${stats.bigH}h — ${stats.bigVal.toFixed(2)} ${varMeta.unit}` : "—"}</CardContent></Card>
            <Card><CardContent className="p-3 text-sm"><div className="text-xs text-muted-foreground">Spread at 24h / 72h / 7d</div>{stats ? `${stats.spreadAt(24)} / ${stats.spreadAt(72)} / ${stats.spreadAt(168)} ${varMeta.unit}` : "—"}</CardContent></Card>
            <Card><CardContent className="p-3 text-sm"><div className="text-xs text-muted-foreground">Run age</div>{stats ? results.map((r: any) => r.forecasts?.[0]?.initTime || r.analysisTimes?.[0] || "n/a").join(", ") : "—"}</CardContent></Card>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={exportCsv}>Download CSV</Button>
            <Button variant="secondary" size="sm" onClick={copyJson}>Copy as JSON</Button>
            <Button variant="secondary" size="sm" onClick={copyLink}>Copy shareable link</Button>
          </div>
        </main>
      </div>

      {showHowTo && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowHowTo(false)}>
          <Card className="max-w-lg m-4" onClick={(e) => e.stopPropagation()}>
            <CardHeader><CardTitle>How to read this</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div><strong>What a fan chart is</strong><p className="text-muted-foreground">An ensemble forecast shown as a median line with shaded 50% and 90% bands. Wider fan = less self-agreement.</p></div>
              <div><strong>What "agreement" means</strong><p className="text-muted-foreground">Two measures: ensemble spread and inter-model deviation. Both must be small for high confidence.</p></div>
              <div><strong>Why a narrow band isn't the same as being right</strong><p className="text-muted-foreground">A tight ensemble can share a bias. Narrow means precise, not correct. Compare against the analysis line.</p></div>
              <Button size="sm" onClick={() => setShowHowTo(false)}>Close</Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
