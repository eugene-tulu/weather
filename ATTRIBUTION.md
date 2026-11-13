# Attribution

This project reads forecast, analysis, and geocoding data from third-party providers. It does not redistribute the raw archives; it displays point time series and derived statistics. Verify the current license for each product before redistributing data or building a commercial product.

## Weather data

Data is accessed through the [Dynamical point API](https://dynamical.org/api/), a free, keyless API over cloud-optimized weather archives.

- **NOAA GFS, HRRR, and GEFS** — [Dynamical catalog](https://dynamical.org/catalog/). NOAA products are generally published under CC-BY-4.0; confirm the license on the specific catalog entry.
- **ECMWF AIFS and IFS ENS** — [Dynamical catalog](https://dynamical.org/catalog/). ECMWF data is subject to ECMWF copyright and terms; confirm the license and any required acknowledgement before redistribution.
- **DWD ICON-EU** — [Dynamical catalog](https://dynamical.org/catalog/). DWD open-data terms apply; confirm the current license.

The app displays model names and values for exploration and comparison. It does not claim that any model is "correct"; forecasts can all be wrong in the same direction.

## Geocoding

City search uses [Open-Meteo's geocoding API](https://open-meteo.com/), which is generally available under CC-BY-4.0. Confirm the current terms before redistribution.

## Software

The application code in this repository is MIT-licensed. Third-party packages retain their own licenses. The UI uses shadcn-style components built on Base UI, Tailwind CSS, Recharts, and Lucide icons.

## Disclaimer

This is not a safety-critical weather service. Do not use it for aviation, marine, emergency response, or other decisions where an official warning is required. Always consult your national weather service.