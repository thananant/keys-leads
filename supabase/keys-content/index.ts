// Edge Function: keys-content  (Supabase project: cloudbeds-rm)
// Backend for the content approval page (content/index.html). Same team code as keys-crm.
//
//   GET  ?action=list                          -> settings, facts, clips, recent fact changes
//   POST ?action=clip   {code, op, ...}        -> approve | reject | revise | posted | remove | keep | unpost
//   POST ?action=fact   {key, label, value}    -> add/edit a manual fact (auto facts come from the keys system)
//   POST ?action=settings {clips_per_month, post_times, avatar_name, mascot_name, brief}
//
// Tables (service-role only): mkt_settings, mkt_facts, mkt_fact_changes, mkt_content — see schema.sql
import { createClient } from "jsr:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type, x-team-code, x-staff",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
  auth: { persistSession: false },
});

function safeEqual(a: string, b: string) {
  if (!a || !b || a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}
async function sha256(t: string) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
const str = (v: unknown, max: number) => (typeof v === "string" ? v.trim().slice(0, max) : "");

type Clip = { code: string; status: string; stale: boolean; history: unknown[]; planned_for: string | null };

// which status changes the page may make, and from where
const OPS: Record<string, { from: string[]; to: string }> = {
  approve: { from: ["idea"], to: "approved" },
  reject: { from: ["idea", "revise", "approved"], to: "rejected" },
  revise: { from: ["idea", "approved", "review", "scheduled"], to: "revise" },
  posted: { from: ["approved", "producing", "review", "scheduled"], to: "posted" },
  remove: { from: ["posted"], to: "removed" },
  unpost: { from: ["posted"], to: "approved" },
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const url = new URL(req.url);
  const action = url.searchParams.get("action") || "";
  try {
    const { data: tc } = await db.from("crm_settings").select("value").eq("key", "team_code_sha256").maybeSingle();
    if (!safeEqual(await sha256((req.headers.get("x-team-code") || "").trim().toUpperCase()), String(tc?.value || ""))) {
      return json({ error: "wrong team code" }, 401);
    }
    let by = "ทีม";
    try { by = str(decodeURIComponent(req.headers.get("x-staff") || ""), 40) || by; } catch { /* keep default */ }

    if (action === "list") {
      const [s, f, c, ch] = await Promise.all([
        db.from("mkt_settings").select("*").eq("id", 1).single(),
        db.from("mkt_facts").select("*").order("source").order("key"),
        db.from("mkt_content").select("*").neq("status", "removed").order("created_at", { ascending: false }).limit(300),
        db.from("mkt_fact_changes").select("*").order("changed_at", { ascending: false }).limit(50),
      ]);
      for (const r of [s, f, c, ch]) if (r.error) throw r.error;
      return json({ ok: true, settings: s.data, facts: f.data, clips: c.data, changes: ch.data });
    }

    if (req.method !== "POST") return json({ error: "POST only" }, 405);
    const body = await req.json().catch(() => ({}));

    if (action === "clip") {
      const code = str(body.code, 12), op = str(body.op, 12);
      const { data: clip, error } = await db.from("mkt_content").select("code, status, stale, history, planned_for").eq("code", code).maybeSingle();
      if (error) throw error;
      if (!clip) return json({ error: "not found" }, 404);
      const c = clip as Clip;
      const note = str(body.note, 1000);
      const now = new Date().toISOString();
      const patch: Record<string, unknown> = { updated_at: now };
      if (op === "keep") {
        // "the old clip is still correct": accept the current facts as its snapshot
        const { data: row } = await db.from("mkt_content").select("fact_keys").eq("code", code).single();
        const { data: snap, error: e2 } = await db.rpc("mkt_snapshot", { p_keys: row!.fact_keys });
        if (e2) throw e2;
        Object.assign(patch, { fact_snapshot: snap, stale: false, stale_reason: null, stale_at: null });
      } else {
        const rule = OPS[op];
        if (!rule) return json({ error: "bad op" }, 400);
        if (!rule.from.includes(c.status)) return json({ error: `ทำไม่ได้จากสถานะ ${c.status}` }, 409);
        if (op === "approve" && c.stale) return json({ error: "ข้อมูลในคลิปนี้เก่าแล้ว ต้องให้ระบบเขียนใหม่ก่อน" }, 409);
        patch.status = rule.to;
        if (op === "approve" && !c.planned_for) {
          const { data: slot, error: e4 } = await db.rpc("mkt_next_slot");
          if (e4) throw e4;
          patch.planned_for = slot;
        }
        if (op === "revise") patch.feedback = note || "ขอแก้";
        if (op === "posted") {
          patch.posted_at = now;
          const urls = typeof body.urls === "object" && body.urls ? body.urls : {};
          patch.post_urls = Object.fromEntries(Object.entries(urls).filter(([k, v]) => /^(facebook|instagram|tiktok)$/.test(k) && typeof v === "string" && /^https:\/\//.test(v as string)).map(([k, v]) => [k, (v as string).slice(0, 300)]));
        }
      }
      patch.history = [...(c.history || []), { at: now, by, what: op, note: note || undefined }];
      const { error: e5 } = await db.from("mkt_content").update(patch).eq("code", code);
      if (e5) throw e5;
      return json({ ok: true });
    }

    if (action === "fact") {
      const key = str(body.key, 40), label = str(body.label, 80), value = str(body.value, 600);
      if (!/^[a-z][a-z0-9_]{1,39}$/.test(key) || !label || !value) return json({ error: "bad input" }, 400);
      const { data: cur } = await db.from("mkt_facts").select("source").eq("key", key).maybeSingle();
      if (cur?.source === "auto") return json({ error: "ข้อนี้ดึงจากระบบ keys อัตโนมัติ แก้ที่ระบบ keys แทน" }, 409);
      const { error } = await db.from("mkt_facts").upsert({ key, label, value, source: "manual", updated_by: by });
      if (error) throw error;
      return json({ ok: true });
    }

    if (action === "settings") {
      const per = Number(body.clips_per_month);
      const times = Array.isArray(body.post_times) ? body.post_times.filter((t: unknown) => typeof t === "string" && /^\d{2}:\d{2}$/.test(t)).slice(0, 4) : null;
      const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
      if (Number.isInteger(per) && per >= 1 && per <= 60) patch.clips_per_month = per;
      if (times?.length) patch.post_times = times;
      for (const k of ["avatar_name", "mascot_name"]) if (str(body[k], 40)) patch[k] = str(body[k], 40);
      if (typeof body.brief === "string") patch.brief = str(body.brief, 2000);
      const { error } = await db.from("mkt_settings").update(patch).eq("id", 1);
      if (error) throw error;
      return json({ ok: true });
    }
    return json({ error: "unknown action" }, 400);
  } catch (e) {
    return json({ error: String((e as Error)?.message || e) }, 500);
  }
});
