import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { Plus, MapPin } from "lucide-react";
import { api, post } from "./api";
import { SourceFields } from "./Workspaces";
maplibregl.setWorkerUrl(mapWorkerUrl);
maplibregl.setWorkerCount(1);

export default function MapWorkspace({
  evidence,
  selectEvidence,
  notify,
}: {
  evidence: any[];
  selectEvidence: (id: string) => void;
  notify: (s: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map | null>(null),
    markers = useRef<maplibregl.Marker[]>([]);
  const [places, setPlaces] = useState<any[]>([]),
    [active, setActive] = useState<any>(null),
    [form, setForm] = useState(false),
    [error, setError] = useState("");
  const [draft, setDraft] = useState({
    title: "",
    longitude: -118.125,
    latitude: 34.137,
    evidence_id: "",
    quote: "",
    category: "Public institution",
    precision: "Approximate institution location",
  });
  const load = () =>
    api("/places")
      .then(setPlaces)
      .catch((e) => notify(e.message));
  useEffect(() => {
    load();
    if (!container.current) return;
    try {
      const m = new maplibregl.Map({
        container: container.current,
        center: [-108, 35],
        zoom: 2.3,
        style: {
          version: 8,
          sources: {
            land: {
              type: "geojson",
              data: "/maps/natural-earth-countries.geojson",
            },
          },
          layers: [
            {
              id: "background",
              type: "background",
              paint: { "background-color": "#0a1521" },
            },
            {
              id: "countries",
              type: "fill",
              source: "land",
              paint: { "fill-color": "#1d3043", "fill-opacity": 0.9 },
            },
            {
              id: "borders",
              type: "line",
              source: "land",
              paint: { "line-color": "#375069", "line-width": 0.7 },
            },
          ],
        },
        attributionControl: false,
      });
      m.addControl(new maplibregl.NavigationControl(), "top-right");
      m.addControl(
        new maplibregl.AttributionControl({
          customAttribution: "Natural Earth · public domain · offline basemap",
        }),
      );
      m.on("error", (e) => setError(e.error.message));
      map.current = m;
      const resize = new ResizeObserver(() => m.resize());
      resize.observe(container.current);
      return () => {
        resize.disconnect();
        markers.current.forEach((x) => x.remove());
        m.remove();
        map.current = null;
      };
    } catch (e: any) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    markers.current.forEach((x) => x.remove());
    markers.current = [];
    if (!map.current) return;
    for (const place of places) {
      const button = document.createElement("button");
      button.className = "sourced-map-marker";
      button.title = place.title;
      button.setAttribute("aria-label", place.title);
      button.textContent = "●";
      button.addEventListener("click", () => setActive(place));
      markers.current.push(
        new maplibregl.Marker({ element: button })
          .setLngLat([place.longitude, place.latitude])
          .addTo(map.current),
      );
    }
  }, [places]);
  return (
    <div className="lab-page map-workspace">
      <div className="lab-heading">
        <div>
          <span className="eyebrow">GEOSPATIAL INTELLIGENCE</span>
          <h2>Place the evidence in context.</h2>
          <p>
            Public institutions, historical places and documented events. Every
            pin opens its supporting source.
          </p>
        </div>
        <button className="button" onClick={() => setForm(!form)}>
          <Plus size={14} /> Add sourced place
        </button>
      </div>
      <div className="map-layout">
        <div className="institution-map" ref={container} />
        <div className="place-list">
          <span className="eyebrow">{places.length} SOURCE-LINKED PLACES</span>
          {places.map((p) => (
            <button
              key={p.id}
              className={active?.id === p.id ? "active" : ""}
              onClick={() => {
                setActive(p);
                map.current?.flyTo({
                  center: [p.longitude, p.latitude],
                  zoom: 8,
                });
              }}
            >
              <MapPin size={15} />
              <div>
                <strong>{p.title}</strong>
                <small>{p.precision}</small>
              </div>
            </button>
          ))}
          {!places.length && (
            <p>
              Add a public place supported by an acquired original. Coordinates
              remain labeled as investigator-entered.
            </p>
          )}
        </div>
      </div>
      {error && <p className="notice">Map rendering: {error}</p>}
      {active && (
        <div className="temporal-detail">
          <div>
            <span className="eyebrow">
              {active.category} · {active.status}
            </span>
            <h3>{active.title}</h3>
            <p>
              {active.latitude.toFixed(5)}, {active.longitude.toFixed(5)} ·{" "}
              {active.precision}
            </p>
            <p>{active.coordinate_method}</p>
            {active.citations.map((c: any) => (
              <blockquote key={c.id}>{c.quote}</blockquote>
            ))}
          </div>
          <button
            className="button"
            onClick={() => selectEvidence(active.evidence_id)}
          >
            Inspect supporting original →
          </button>
        </div>
      )}
      {form && (
        <form
          className="lab-form"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await post("/places", draft);
              setForm(false);
              load();
              notify("Source-linked public place saved");
            } catch (e: any) {
              notify(e.message);
            }
          }}
        >
          <h3>Map a public institution or historical event</h3>
          <label>
            Public place name
            <input
              required
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </label>
          <div className="form-grid">
            <label>
              Longitude
              <input
                type="number"
                required
                min="-180"
                max="180"
                step="any"
                value={draft.longitude}
                onChange={(e) =>
                  setDraft({ ...draft, longitude: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Latitude
              <input
                type="number"
                required
                min="-85"
                max="85"
                step="any"
                value={draft.latitude}
                onChange={(e) =>
                  setDraft({ ...draft, latitude: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Public place category
              <select
                value={draft.category}
                onChange={(e) =>
                  setDraft({ ...draft, category: e.target.value })
                }
              >
                {["Public institution", "Public event", "Historical place"].map(
                  (c) => (
                    <option key={c}>{c}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              Coordinate precision
              <input
                value={draft.precision}
                onChange={(e) =>
                  setDraft({ ...draft, precision: e.target.value })
                }
              />
            </label>
          </div>
          <SourceFields
            evidence={evidence}
            value={draft}
            onChange={(v) => setDraft({ ...draft, ...v })}
          />
          <button className="button primary">Save source-linked place</button>
          <p className="muted">
            The source passage establishes the place association. Coordinates
            and precision are your explicit interpretation.
          </p>
        </form>
      )}
    </div>
  );
}
