export const api = async (path: string, options?: RequestInit) => {
  const r = await fetch("/api" + path, options);
  if (!r.ok) {
    const e = await r.json();
    throw new Error(
      typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail),
    );
  }
  return r.json();
};
export const post = (path: string, data: any) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
