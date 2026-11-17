import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "1m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<750"],
  },
};

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const API_KEY = __ENV.API_KEY || "";

export default function () {
  const health = http.get(`${BASE}/health/live`);
  check(health, { "health 200": (r) => r.status === 200 });

  if (API_KEY) {
    const sites = http.get(`${BASE}/v1/sites`, {
      headers: { "X-API-Key": API_KEY },
    });
    check(sites, { "sites 200": (r) => r.status === 200 });
  }

  sleep(1);
}
