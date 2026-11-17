import type { Metadata } from "next";

import { MapView } from "@/components/map/MapView";

export const metadata: Metadata = {
  title: "Weather map | Disagreement",
  description:
    "Explore map-optimized Icechunk forecasts from NOAA GFS/GEFS and ECMWF AIFS/IFS ENS.",
};

export default function MapPage() {
  return <MapView />;
}
