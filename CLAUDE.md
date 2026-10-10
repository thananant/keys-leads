# keys Lead Finder — กติกาการทำงาน

ระบบหาลูกค้าและติดตามการขายของ **keys** (ขายให้โรงแรมที่ใช้ Cloudbeds)
**ไม่เกี่ยวกับ Mix888 หรือจริงใจหมูกระทะ** ห้ามใช้ Supabase/LINE ของสองระบบนั้น

## ผู้ใช้สั่งงานจาก iPhone
- **งานทุกชิ้นต้องอัปขึ้น GitHub ทุกครั้งโดยไม่ต้องถาม:** commit → push branch → PR → merge เข้า `main`
- จบงานส่งลิงก์ที่เปิดบนมือถือได้เสมอ
  - เว็บ: https://thananant.github.io/keys-leads/
  - ไฟล์อื่น: `https://github.com/thananant/keys-leads/blob/main/<path>`
- ตอบภาษาไทย สั้น อ่านง่ายบนจอมือถือ
- ข้อความภาษาอังกฤษที่อ่านไม่ออก มักเป็นภาษาไทยที่ลืมสลับแป้น (เช่น `wfhc]t` = "ได้แล้ว")

## ข้อควรระวัง
- repo นี้เป็น **Public** ห้ามใส่ token, รหัสทีม, cron key หรือข้อมูลลับใด ๆ
- Backend: Supabase project **cloudbeds-rm** (`vauqbfjgkdhgrtycqhnd`)
  - edge function `keys-crm` (โค้ดอยู่ที่ `supabase/keys-crm/index.ts` deploy ผ่าน Supabase MCP)
  - ตาราง `crm_leads`, `crm_settings`, `crm_reminder_log`
  - รหัสทีมกับ cron key อยู่ใน `crm_settings` เท่านั้น
  - LINE token อยู่ใน Edge Function secrets

## โครงสร้าง
- `lead-finder.template.html` คือหน้าเว็บ (`__DATA__` = ข้อมูลโรงแรม)
  - `python3 build.py` สร้าง `index.html` (Pages), `lead-finder.html` (claude.ai artifact), `.xlsx`, `.csv`
- `data/hotels.json` = ข้อมูลโรงแรม · `data/phones-*.json` = ข้อมูลติดต่อ · เหตุผลที่เสนอแต่ละโรงแรมสร้างใน `build.py`
- `apify/find_leads.py` + `.github/workflows/find-leads.yml` = หาโรงแรมที่ใช้ Cloudbeds เพิ่ม (ต้องมี secret `APIFY_TOKEN`)
- งานที่ยังค้าง/วิธีตั้งค่า: `SETUP.md`
