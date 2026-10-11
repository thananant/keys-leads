// "Find more leads": Google Maps search through Apify, then a booking-engine check of each website.
// Started from the page (action=search), advanced by pg_cron every minute (action=search-tick).
import type { SupabaseClient } from "jsr:@supabase/supabase-js@2";

const ACTOR = "compass~crawler-google-places";
const CHECKS_PER_TICK = 30;

export const KHET: Record<string, string> = {
  "Phra Nakhon": "พระนคร", "Dusit": "ดุสิต", "Nong Chok": "หนองจอก", "Bang Rak": "บางรัก", "Bang Khen": "บางเขน",
  "Bang Kapi": "บางกะปิ", "Pathum Wan": "ปทุมวัน", "Pom Prap Sattru Phai": "ป้อมปราบศัตรูพ่าย", "Phra Khanong": "พระโขนง",
  "Min Buri": "มีนบุรี", "Lat Krabang": "ลาดกระบัง", "Yan Nawa": "ยานนาวา", "Samphanthawong": "สัมพันธวงศ์", "Phaya Thai": "พญาไท",
  "Thon Buri": "ธนบุรี", "Bangkok Yai": "บางกอกใหญ่", "Huai Khwang": "ห้วยขวาง", "Khlong San": "คลองสาน", "Taling Chan": "ตลิ่งชัน",
  "Bangkok Noi": "บางกอกน้อย", "Bang Khun Thian": "บางขุนเทียน", "Phasi Charoen": "ภาษีเจริญ", "Nong Khaem": "หนองแขม",
  "Rat Burana": "ราษฎร์บูรณะ", "Bang Phlat": "บางพลัด", "Din Daeng": "ดินแดง", "Bueng Kum": "บึงกุ่ม", "Sathon": "สาทร",
  "Bang Sue": "บางซื่อ", "Chatuchak": "จตุจักร", "Bang Kho Laem": "บางคอแหลม", "Prawet": "ประเวศ", "Khlong Toei": "คลองเตย",
  "Suan Luang": "สวนหลวง", "Chom Thong": "จอมทอง", "Don Mueang": "ดอนเมือง", "Ratchathewi": "ราชเทวี", "Lat Phrao": "ลาดพร้าว",
  "Watthana": "วัฒนา", "Bang Khae": "บางแค", "Lak Si": "หลักสี่", "Sai Mai": "สายไหม", "Khan Na Yao": "คันนายาว",
  "Saphan Sung": "สะพานสูง", "Wang Thonglang": "วังทองหลาง", "Khlong Sam Wa": "คลองสามวา", "Bang Na": "บางนา",
  "Thawi Watthana": "ทวีวัฒนา", "Thung Khru": "ทุ่งครุ", "Bang Bon": "บางบอน",
};
const ALIASES: Record<string, string> = {
  "pathumwan": "Pathum Wan", "sathorn": "Sathon", "yannawa": "Yan Nawa", "thonburi": "Thon Buri", "vadhana": "Watthana",
  "wattana": "Watthana", "klong toey": "Khlong Toei", "khlong toey": "Khlong Toei", "bangrak": "Bang Rak", "ratchatewi": "Ratchathewi",
  "huaikhwang": "Huai Khwang", "huai khwang": "Huai Khwang", "don muang": "Don Mueang", "ladprao": "Lat Phrao", "phrakhanong": "Phra Khanong",
  "bangna": "Bang Na", "ratchathewi": "Ratchathewi", "phayathai": "Phaya Thai",
};
const ENGINES: [string, RegExp][] = [
  ["SiteMinder", /book-directonline\.com|thebookingbutton\.com|siteminder/i],
  ["Little Hotelier", /littlehotelier\.com/i],
  ["SynXis", /synxis\.com/i],
  ["TravelClick", /travelclick\.com|ihotelier/i],
  ["eZee", /ipms247\.com|ezeetechnosys|live\.ipms/i],
  ["STAAH", /staah\.(?:net|com)/i],
  ["Simple Booking", /simplebooking\.it/i],
  ["HotelRunner", /hotelrunner\.com/i],
  ["eviivo", /eviivo\.com/i],
  ["Hotelogix", /hotelogix/i],
  ["Mews", /mews\.(?:li|com)/i],
];
const CB_RE = /cloudbeds\.com\/(?:[a-z]{2}\/)?reservation\/([A-Za-z0-9]{5,8})/;
const UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

const apifyToken = () => Deno.env.get("APIFY_TOKEN") || "";
async function apify(path: string, init?: RequestInit) {
  const sep = path.includes("?") ? "&" : "?";
  const r = await fetch(`https://api.apify.com/v2${path}${sep}token=${apifyToken()}`, init);
  if (!r.ok) throw new Error(`Apify ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export function estimate(districts: number, kinds: number, max: number) {
  const places = districts * kinds * max;
  return { places, usd: Math.round(places * 0.004 * 10) / 10 }; // Google Maps scraper ≈ $4 / 1,000 places
}

export async function startSearch(db: SupabaseClient, body: { districts?: string[]; max?: number; kinds?: string[]; by?: string }) {
  if (!apifyToken()) return { ok: false, error: "ยังไม่ได้ใส่ APIFY_TOKEN ใน Supabase" };
  const active = await db.from("crm_search_runs").select("id").in("status", ["starting", "scraping", "loading", "checking"]).limit(1);
  if (active.data?.length) return { ok: false, error: "มีการค้นหาที่ยังทำงานอยู่ รอให้เสร็จก่อน" };
  const districts = (body.districts || []).filter((d) => KHET[d]);
  if (!districts.length) return { ok: false, error: "เลือกอย่างน้อย 1 เขต" };
  const kinds = (body.kinds?.length ? body.kinds : ["hotel", "hostel", "serviced apartment"]).slice(0, 4);
  const max = Math.min(Math.max(Number(body.max) || 40, 5), 120);
  const searches = districts.flatMap((d) => kinds.map((k) => `${k} in ${d} Bangkok`));
  const { data: row, error } = await db.from("crm_search_runs")
    .insert({ status: "starting", params: { districts, kinds, max, est: estimate(districts.length, kinds.length, max) }, started_by: body.by || null })
    .select("id").single();
  if (error) throw error;
  try {
    const run = await apify(`/acts/${ACTOR}/runs`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ searchStringsArray: searches, maxCrawledPlacesPerSearch: max, language: "en", countryCode: "th", skipClosedPlaces: true }),
    });
    await db.from("crm_search_runs").update({ status: "scraping", apify_run_id: run.data.id, dataset_id: run.data.defaultDatasetId, updated_at: new Date().toISOString() }).eq("id", row.id);
    return { ok: true, id: row.id };
  } catch (e) {
    await db.from("crm_search_runs").update({ status: "failed", error: String((e as Error).message), updated_at: new Date().toISOString() }).eq("id", row.id);
    return { ok: false, error: String((e as Error).message) };
  }
}

function khetOf(p: Record<string, unknown>, fallback: string) {
  const names: Record<string, string> = { ...Object.fromEntries(Object.keys(KHET).map((k) => [k.toLowerCase(), k])), ...ALIASES };
  const segs = String(p.address || "").split(",").map((s) => s.trim()).reverse();
  for (const s of segs) {
    const k = s.replace(/^(khet|district)\s+|\s+(district|\d{5}).*$/gi, "").trim().toLowerCase();
    if (names[k]) return names[k];
  }
  const hay = [p.address, p.neighborhood, p.street, p.city].join(" ").toLowerCase();
  for (const [a, real] of Object.entries(names)) if (hay.includes(a)) return real;
  return fallback;
}
function kindOf(cat: unknown) {
  const c = String(cat || "").toLowerCase();
  if (c.includes("hostel") || c.includes("guest")) return "hostel";
  if (c.includes("apartment")) return "apt";
  if (c.includes("boutique")) return "boutique";
  return "hotel";
}
async function fetchText(url: string): Promise<[string, string]> {
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 10000);
    const r = await fetch(url, { headers: { "User-Agent": UA, "Accept-Language": "en,th" }, signal: ctl.signal, redirect: "follow" });
    clearTimeout(t);
    const txt = (await r.text()).slice(0, 600_000);
    return [txt, r.url || url];
  } catch { return ["", url]; }
}
async function detect(site: string): Promise<{ engine: string; code: string | null }> {
  const [html, final] = await fetchText(site);
  if (!html) return { engine: "unreachable", code: null };
  const pages = [html];
  const links = [...html.matchAll(/href=["']([^"']+)["']/gi)].map((m) => m[1]);
  const host = (() => { try { return new URL(final).host; } catch { return ""; } })();
  const book = [...new Set(links.filter((l) => /book|reserv|จอง|availability/i.test(l)).map((l) => { try { return new URL(l, final).href; } catch { return ""; } }).filter(Boolean))].slice(0, 2);
  for (const b of book) {
    const m = b.match(CB_RE); if (m) return { engine: "Cloudbeds", code: m[1] };
    if (new URL(b).host === host) pages.push((await fetchText(b))[0]);
  }
  const text = pages.join("\n");
  const m = text.match(CB_RE); if (m) return { engine: "Cloudbeds", code: m[1] };
  if (/cloudbeds/i.test(text)) return { engine: "Cloudbeds (no code)", code: null };
  for (const [name, rx] of ENGINES) if (rx.test(text)) return { engine: name, code: null };
  return { engine: "unknown", code: null };
}

export async function tick(db: SupabaseClient, knownIds: Set<string>) {
  const { data: run } = await db.from("crm_search_runs").select("*").in("status", ["starting", "scraping", "loading", "checking"]).order("id").limit(1).maybeSingle();
  if (!run) return { idle: true };
  const upd = (f: Record<string, unknown>) => db.from("crm_search_runs").update({ ...f, updated_at: new Date().toISOString() }).eq("id", run.id);

  if (run.status === "starting") {
    // never got an Apify run id (start crashed) → give up after 10 minutes
    if (Date.now() - new Date(run.created_at).getTime() > 600_000) await upd({ status: "failed", error: "start timed out" });
    return { run: run.id, status: run.status };
  }
  if (run.status === "scraping") {
    const st = (await apify(`/actor-runs/${run.apify_run_id}`)).data.status;
    if (st === "SUCCEEDED") { await upd({ status: "loading" }); run.status = "loading"; }
    else if (["FAILED", "ABORTED", "TIMED-OUT"].includes(st)) { await upd({ status: "failed", error: `Apify ${st}` }); return { run: run.id, status: "failed" }; }
    else return { run: run.id, status: "scraping", apify: st };
  }
  if (run.status === "loading") {
    const items: Record<string, unknown>[] = await apify(`/datasets/${run.dataset_id}/items?clean=true&format=json&limit=500&offset=${run.offset_loaded}`);
    const rows = items.map((p) => ({
      place_key: String(p.placeId || p.url || p.title), run_id: run.id, data: p,
      website: (p.website as string) || null, status: p.website ? "pending" : "done",
    }));
    if (rows.length) await db.from("crm_places").upsert(rows, { onConflict: "place_key", ignoreDuplicates: true });
    const loaded = run.offset_loaded + items.length;
    const { count } = await db.from("crm_places").select("place_key", { count: "exact", head: true }).eq("run_id", run.id);
    await upd({ offset_loaded: loaded, places: count || 0, status: items.length < 500 ? "checking" : "loading" });
    return { run: run.id, status: "loading", loaded };
  }
  // checking
  const { data: pending } = await db.from("crm_places").select("place_key, data, website").eq("run_id", run.id).eq("status", "pending").limit(CHECKS_PER_TICK);
  if (!pending?.length) { await upd({ status: "done" }); return { run: run.id, status: "done" }; }
  const results = await Promise.all(pending.map((p) => detect(p.website!)));
  let found = 0;
  for (let i = 0; i < pending.length; i++) {
    const p = pending[i], r = results[i], d = p.data as Record<string, unknown>;
    await db.from("crm_places").update({ engine: r.engine, cb_code: r.code, status: "done", checked_at: new Date().toISOString() }).eq("place_key", p.place_key);
    if (r.code && !knownIds.has(r.code)) {
      const fallback = String(d.searchString || "").split(" in ").pop()?.replace(" Bangkok", "") || "Bangkok";
      const en = khetOf(d, fallback);
      const stars = String(d.hotelStars || "").match(/(\d(?:\.\d)?)/);
      const phone = String(d.phone || "").replace(/^\+66\s*/, "0").trim() || null;
      const rec = {
        id: r.code, n: d.title, ken: en, kth: KHET[en] || en, t: kindOf(d.categoryName),
        s: stars ? Number(stars[1]) : null, rv: d.totalScore ? Math.round(Number(d.totalScore) * 20) / 10 : null,
        rc: d.reviewsCount ?? null, src: d.totalScore ? "Google" : "", p: null, rm: null, a: d.address || "",
        u: `https://hotels.cloudbeds.com/reservation/${r.code}`, ph: phone, ph2: null, em: null, ln: null, web: p.website,
        no: `พบจากการค้นหาในระบบ (Google Maps) · ${d.categoryName || ""}`.replace(/ · $/, ""), isNew: true,
      };
      const ins = await db.from("crm_found_hotels").upsert({ id: r.code, data: rec, run_id: run.id }, { onConflict: "id", ignoreDuplicates: true });
      if (!ins.error) found++;
    }
  }
  await upd({ checked: run.checked + pending.length, found: run.found + found });
  return { run: run.id, status: "checking", checked: pending.length, found };
}

export async function status(db: SupabaseClient) {
  const { data } = await db.from("crm_search_runs").select("id,status,params,places,checked,found,error,started_by,created_at,updated_at").order("id", { ascending: false }).limit(5);
  const { data: eng } = await db.rpc("crm_engine_counts");
  return { runs: data || [], engines: eng || [], apify_ready: !!apifyToken() };
}
