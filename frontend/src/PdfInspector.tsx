import { useEffect, useRef, useState } from "react";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { ChevronLeft, ChevronRight, Search, Minus, Plus } from "lucide-react";
GlobalWorkerOptions.workerSrc = workerUrl;
const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

export default function PdfInspector({
  evidence,
  focus = "",
}: {
  evidence: any;
  focus?: string;
}) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null),
    [page, setPage] = useState(1),
    [zoom, setZoom] = useState(0.8),
    [query, setQuery] = useState(focus),
    [error, setError] = useState(""),
    [size, setSize] = useState({ width: 0, height: 0 }),
    [boxes, setBoxes] = useState<any[]>([]);
  const canvas = useRef<HTMLCanvasElement>(null),
    rendering = useRef<RenderTask | null>(null),
    pageScroll = useRef<HTMLDivElement>(null);
  const pages = evidence.metadata.pages || [];
  const matches = query
    ? pages.filter((p: any) => norm(p.text).includes(norm(query)))
    : [];
  useEffect(() => {
    let disposed = false;
    setDoc(null);
    setPage(1);
    setError("");
    setQuery(focus);
    const loading = getDocument({
      url: evidence.fileUrl,
      wasmUrl: "/pdf-assets/wasm/",
      standardFontDataUrl: "/pdf-assets/standard_fonts/",
      cMapUrl: "/pdf-assets/cmaps/",
      cMapPacked: true,
      maxImageSize: 40000000,
      disableAutoFetch: true,
      disableStream: true,
    });
    loading.promise
      .then((d) => {
        if (disposed) {
          return;
        }
        setDoc(d);
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      });
    return () => {
      disposed = true;
      rendering.current?.cancel();
      loading.destroy();
    };
  }, [evidence.id]);
  useEffect(() => {
    setQuery(focus);
    const found = pages.find(
      (p: any) => focus && norm(p.text).includes(norm(focus)),
    );
    if (found) setPage(found.page);
  }, [focus, evidence.id]);
  useEffect(() => {
    let disposed = false;
    rendering.current?.cancel();
    if (!doc || !canvas.current) return;
    doc
      .getPage(page)
      .then(async (p) => {
        if (disposed || !canvas.current) return;
        const viewport = p.getViewport({ scale: zoom });
        const c = canvas.current;
        delete c.dataset.rendered;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        c.width = viewport.width * ratio;
        c.height = viewport.height * ratio;
        c.style.width = `${viewport.width}px`;
        c.style.height = `${viewport.height}px`;
        setSize({ width: viewport.width, height: viewport.height });
        const blocks = pages.find((x: any) => x.page === page)?.blocks || [];
        setBoxes(
          blocks
            .filter((b: any) => query && norm(b.text).includes(norm(query)))
            .map((b: any) => {
              const [x1, y1] = viewport.convertToViewportPoint(
                p.view[0] + b.bbox[0],
                p.view[3] - b.bbox[1],
              );
              const [x2, y2] = viewport.convertToViewportPoint(
                p.view[0] + b.bbox[2],
                p.view[3] - b.bbox[3],
              );
              return {
                left: Math.min(x1, x2),
                top: Math.min(y1, y2),
                width: Math.abs(x2 - x1),
                height: Math.abs(y2 - y1),
                text: b.text,
              };
            }),
        );
        const task = p.render({
          canvas: c,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        rendering.current = task;
        try {
          await task.promise;
          if (!disposed) c.dataset.rendered = String(page);
        } catch (e: any) {
          if (e.name !== "RenderingCancelledException" && !disposed)
            setError(e.message);
        }
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      });
    return () => {
      disposed = true;
      rendering.current?.cancel();
    };
  }, [doc, page, zoom, query]);
  useEffect(() => {
    if (!query || !boxes.length || !pageScroll.current) return;
    pageScroll.current.scrollTop = Math.max(0, boxes[0].top - 35);
    pageScroll.current.scrollLeft = Math.max(0, boxes[0].left - 25);
  }, [boxes, query]);
  return (
    <div className="pdf-inspector">
      <div className="pdf-navigation">
        <button
          title="Previous PDF page"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          <ChevronLeft size={15} />
        </button>
        <label>
          Page{" "}
          <input
            aria-label="PDF page number"
            type="number"
            min="1"
            max={doc?.numPages || 1}
            value={page}
            onChange={(e) =>
              setPage(
                Math.max(
                  1,
                  Math.min(doc?.numPages || 1, Number(e.target.value) || 1),
                ),
              )
            }
          />{" "}
          / {doc?.numPages || "…"}
        </label>
        <button
          title="Next PDF page"
          disabled={!doc || page >= doc.numPages}
          onClick={() => setPage(page + 1)}
        >
          <ChevronRight size={15} />
        </button>
        <button
          title="Zoom PDF out"
          onClick={() => setZoom(Math.max(0.3, zoom - 0.2))}
        >
          <Minus size={13} />
        </button>
        <span>{Math.round(zoom * 100)}%</span>
        <button
          title="Zoom PDF in"
          onClick={() => setZoom(Math.min(2.5, zoom + 0.2))}
        >
          <Plus size={13} />
        </button>
      </div>
      <label className="pdf-search">
        <Search size={13} />
        <input
          aria-label="Search preserved PDF"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search source text / cited passage"
        />
      </label>
      {query && (
        <div className="pdf-search-results">
          {matches.length ? (
            matches.map((p: any) => (
              <button key={p.page} onClick={() => setPage(p.page)}>
                Page {p.page}
              </button>
            ))
          ) : (
            <span>No extracted-text matches</span>
          )}
        </div>
      )}
      {error && <p className="notice">PDF rendering: {error}</p>}
      <div className="pdf-page-scroll" ref={pageScroll}>
        <div
          className="pdf-paper"
          style={{ width: size.width || 250, height: size.height || 350 }}
        >
          <canvas ref={canvas} aria-label={`Original PDF page ${page}`} />
          {boxes.map((b, i) => (
            <div
              key={i}
              className="pdf-passage-highlight"
              style={b}
              title={b.text}
            />
          ))}
        </div>
      </div>
      <p className="pdf-caption">
        Actual preserved PDF · extracted block coordinates · {boxes.length}{" "}
        highlighted blocks. OCR matches without coordinates appear in search
        results.
      </p>
    </div>
  );
}
