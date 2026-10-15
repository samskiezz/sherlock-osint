import httpx, json

c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=40)
sources = [
    (
        "Caltech · Tridroid Cup original institutional report",
        "https://mce.caltech.edu/news/tridroid-cup-robots-play-soccer",
    ),
    (
        "Mondaloy · patent US20030053926A1",
        "https://patents.google.com/patent/US20030053926A1/en",
    ),
    (
        "NASA · Apollo 11 mission report (processing fixture)",
        "https://ntrs.nasa.gov/api/citations/19710015566/downloads/19710015566.pdf",
    ),
    (
        "NASA · Apollo 11 lunar photograph (processing fixture)",
        "https://www.nasa.gov/wp-content/uploads/2023/03/5902main_a11-40-5886_full.jpg",
    ),
    (
        "Steam · Bohrdom public application metadata",
        "https://store.steampowered.com/api/appdetails?appids=945530",
    ),
]
for title, url in sources:
    r = c.post("/api/jobs", json={"title": title, "url": url})
    print(title, r.status_code, r.text)
# Authorized persistent source monitoring, first run immediately; every six hours thereafter.
for name, mode, target in [
    ("Mondaloy · new literature", "crossref", "Mondaloy nickel superalloy"),
    ("Caltech robotics · source version watch", "url", sources[0][1]),
]:
    r = c.post(
        "/api/watches",
        json={"name": name, "mode": mode, "target": target, "interval_minutes": 360},
    )
    print("WATCH", r.status_code, r.text)
