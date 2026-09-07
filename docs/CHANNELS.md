# Real customer channels (milestone 10)

The AI can read your **shop e-mail** and your **Facebook Page / Instagram** messages, draft an answer for each one, and send it
**only after you tap "Approve & send"** on your phone (or type your own version). Nothing is ever sent by itself.

What it does every 3 minutes (when it is not busy):
1. looks for new messages in the connected channels;
2. throws away machine mail (newsletters, auto-replies, bounces, no-reply senders) — you are told only in the daily report;
3. drafts a reply for each real customer message, following your `/policy`, and sends it to your phone with
   **✅ Approve & send · ✏️ Edit · ❌ Reject**;
4. *Approve & send* → the reply goes out (e-mail replies are threaded under the customer's mail with their text quoted);
   *Edit* → your text goes out; *Reject* → nothing happens.

Every message is remembered by its id, so nothing is drafted twice, even after a restart. All counts: `/channels`.

## Connect your shop e-mail (any provider)

Add these lines to `~/businessai/.secrets/env` (the file that already holds the Telegram token):

```
MAIL_USER=shop@yourdomain.com
MAIL_PASSWORD=xxxx xxxx xxxx xxxx
MAIL_IMAP_HOST=imap.yourprovider.com
MAIL_SMTP_HOST=smtp.yourprovider.com
MAIL_FROM_NAME=Your Shop Name
```

Then `sh scripts/service.sh` to restart, and in Telegram `/channels check` — it should say *mailbox ok … sending ok*.

Provider settings:

| provider | IMAP host | SMTP host | password |
|---|---|---|---|
| Gmail / Google Workspace | imap.gmail.com | smtp.gmail.com | an **app password**, not your normal one: turn on 2-Step Verification, then create one at myaccount.google.com/apppasswords (16 characters; spaces don't matter). IMAP is on by default since 2025. |
| Outlook.com / Hotmail | outlook.office365.com | smtp-mail.outlook.com | app password (Security → Advanced security options → App passwords) |
| Aruba (.it) | imaps.aruba.it | smtps.aruba.it (port 465 → add `MAIL_SMTP_PORT=465`) | your mailbox password |
| Libero | imapmail.libero.it | smtp.libero.it | your mailbox password |
| Yahoo | imap.mail.yahoo.com | smtp.mail.yahoo.com | app password |
| iCloud | imap.mail.me.com | smtp.mail.me.com | app-specific password |
| Zoho | imap.zoho.eu | smtp.zoho.eu | app password |
| your own domain (Shopify e-mail forwarding, cPanel…) | ask the provider; usually mail.yourdomain.com | same | mailbox password |

Defaults: IMAP port 993 with SSL, SMTP port 587 with STARTTLS (`MAIL_SMTP_PORT=465` switches to SSL). Optional:
`MAIL_FOLDER=INBOX`, `MAIL_MARK_SEEN=0` if you do not want it to mark the mails it read as read, `CHANNELS_INTERVAL=180` seconds.

Tip: give it its **own** mailbox (e.g. support@yourshop.com) rather than your personal one. It only ever reads *unread* mail
in that folder, and marks what it read as read.

## Connect Facebook Page messages and Instagram DMs

This uses Meta's official Graph API (free). You need a Facebook **Page** (and for Instagram, a professional Instagram account
linked to that Page) plus a Meta developer app — about 20 minutes, once:

1. developers.facebook.com → *My Apps* → *Create App* → type **Business** → give it a name.
2. In the app add the product **Messenger**; under *Messenger → Instagram settings / Messenger API settings* connect your Page.
3. Open *Tools → Graph API Explorer*: choose your app, click **Generate Access Token**, tick the permissions
   `pages_show_list`, `pages_messaging`, `pages_read_engagement`, `pages_manage_metadata` (+ `instagram_basic`,
   `instagram_manage_messages` for Instagram) and log in.
4. Still in the Explorer, choose your Page in the *User or Page* dropdown → you get a **Page access token**. Make it long-lived
   (Access Token Debugger → *Extend Access Token*), otherwise it expires after an hour or so.
5. The Page id is on your Page's *About* page (or `me?fields=id` in the Explorer). For Instagram, the business account id:
   `me?fields=instagram_business_account` with the Page token.

Add to `.secrets/env`:
```
META_PAGE_ID=1234567890
META_PAGE_TOKEN=EAAB...
META_IG_ID=17841400000000000      (only for Instagram)
```
Restart (`sh scripts/service.sh`) and `/channels check` → *page ok — Your Page Name*.

Notes: while the app is in *development mode* only people with a role in the app (you, testers) can message the Page through
the API — good for trying it out; to answer real customers, submit the app for *App Review* (Meta's standard step for the
messaging permissions). Replies are sent as "customer service responses", which Meta allows within 24 hours of the customer's
last message; older conversations have to be answered from the Facebook inbox by hand and the AI tells you when that happens.

## Commands

- `/channels` — what is connected and the counts (received / sent / skipped).
- `/channels check` — connects to the mailbox, the mail sender and the Page once and reports in plain words.
- `/channels now` — looks for new messages immediately instead of waiting for the next 3-minute check.
- `/policy` — the rules every draft obeys (shipping times, returns, tone, sign-off).
- `/stats` — how often you approve, edit or reject the drafts, per kind of message.

## Safety

- Sending happens in exactly one place (`Agent.deliver`), and only after your tap or your typed text.
- Passwords and tokens live in `.secrets/env` (git-ignored) and are removed from every log and message (`config.redact`).
- The AI never sees the addresses or ids it replies to — they stay in the inbox record, not in the model prompt.
- Messages that mention lawyers, chargebacks, injuries, press or personal data are flagged **ESCALATION** in the draft.
- Test everything without any account: `python3 engine/scripts/score_channels.py` runs a fake mail server and a fake Graph
  API on your machine (36 checks).
