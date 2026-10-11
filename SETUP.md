# keys Lead Finder: ตั้งค่าที่เหลือ (ทำบนมือถือได้)

หน้าเว็บ: https://thananant.github.io/keys-leads/

---

## 1. เปิด GitHub Pages (1 นาที)
1. เปิด https://github.com/thananant/keys-leads/settings/pages
2. Source: **Deploy from a branch** · Branch: **main** / **(root)** → **Save**
3. รอ 1–2 นาที แล้วเปิด https://thananant.github.io/keys-leads/

## 2. ใส่ Apify token (2 นาที) เพื่อให้ปุ่ม "หาลูกค้าเพิ่ม" ทำงาน
1. เปิด https://console.apify.com/settings/integrations แล้วกด copy **Personal API token**
2. บอก Claude ว่า "พร้อมใส่ Apify token" แล้ว Claude จะเปิดหน้า Supabase ให้วาง token เอง (ไม่ต้องส่งในแชท)
   - ชื่อ secret: `APIFY_TOKEN`
3. ในหน้าเว็บ ไปที่แท็บ **หาลูกค้าเพิ่ม** → เลือกเขต → กด **เริ่มค้นหา**
   - ระบบทำงานต่อเองแม้ปิดหน้าเว็บ (pg_cron เดินงานทุกนาที)
   - โรงแรม Cloudbeds ที่เจอใหม่จะขึ้นในรายชื่อพร้อมป้าย "ใหม่"

## 3. สร้างบอท LINE ของ keys เพื่อแจ้งเตือนนัด (10 นาที)
1. เข้า https://developers.line.biz/console/ ใน Safari แล้ว login ด้วย LINE
2. **Create a new provider** → ตั้งชื่อ `keys`
3. **Create a Messaging API channel**
   - กรอกชื่อ `keys แจ้งนัด` · หมวด Business
   - ระบบจะสร้าง LINE OA ให้ด้วย
4. ในแท็บ **Messaging API**:
   - **Allow bot to join group chats** → เปิด (Enabled)
   - **Auto-reply messages / Greeting** → ปิด
   - **Webhook URL** → ใส่ `https://vauqbfjgkdhgrtycqhnd.supabase.co/functions/v1/keys-crm?action=line-webhook` แล้วเปิด **Use webhook**
   - **Channel access token** → กด Issue
5. บอก Claude ว่า "พร้อมใส่ LINE token" แล้ว Claude จะส่งลิงก์ Supabase มาให้วางค่าเอง (token ไม่ผ่านแชท) 2 ค่า:
   - `LINE_TOKEN` = Channel access token (แท็บ Messaging API)
   - `LINE_CHANNEL_SECRET` = Channel secret (แท็บ Basic settings)
6. เพิ่มบอทเป็นเพื่อน (สแกน QR ในแท็บ Messaging API) แล้ว **เชิญบอทเข้ากลุ่ม LINE ทีมขาย**
   - บอทจะตอบในกลุ่มว่าพร้อมแจ้งเตือน

หลังจากนั้นทุกวันบอทจะส่งเข้ากลุ่ม:
- **08:00** นัดของวันนี้
- **18:00** นัดของพรุ่งนี้

(ถ้าวันไหนไม่มีนัด จะไม่ส่ง)

---

### เทคนิค (สำหรับ Claude / นักพัฒนา)
- Backend: Supabase project `cloudbeds-rm`
  - ตาราง `crm_leads`, `crm_settings`, `crm_reminder_log` (RLS ปิดทุกสิทธิ์ เข้าได้เฉพาะ service role)
  - edge function `keys-crm` (โค้ดอยู่ที่ `supabase/keys-crm/index.ts`)
- รหัสทีมเก็บเป็น SHA-256 ใน `crm_settings.team_code_sha256`
- pg_cron `keys-crm-remind-morning` (01:00 UTC) และ `keys-crm-remind-evening` (11:00 UTC) เรียก `public.crm_call_remind()`
- หน้าเว็บ: ถ้าไม่ได้ใส่รหัสทีม เก็บใน localStorage ถ้าใส่รหัสทีมแล้ว sync กับ `keys-crm` (ถ้าออฟไลน์ เก็บไว้ในเครื่องก่อน แล้วส่งขึ้นเมื่อกลับมาออนไลน์)
