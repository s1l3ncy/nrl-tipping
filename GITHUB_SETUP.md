# Putting your NRL tipping app online (so it runs with your Mac off)

This moves the automatic updates onto **GitHub's servers**. Once done, the tips
refresh on their own every day and you just open a web link — your MacBook can be
shut down the whole time.

There's only **one** thing I can't do for you: create your account and log in.
Everything else I can do or drive for you. Here's the whole thing, start to finish.

---

## Step 1 — Make a free GitHub account  *(you — ~2 min)*
1. Go to https://github.com/signup
2. Enter an email, a password, and a username (anything, e.g. `joshr-footy`).
3. Verify your email when GitHub asks.
That's it — the free plan is all we need.

## Step 2 — Create the project ("repository")  *(I can drive this once you're logged in)*
1. Top-right **+** → **New repository**.
2. Name it e.g. `nrl-tipping`.
3. Set it to **Public** (this keeps the automatic updates completely free).
4. Click **Create repository**.

## Step 3 — Upload the project files  *(I can drive this)*
1. On the new repo page, click **uploading an existing file**.
2. Drag in EVERYTHING from your "Footy tipping project" folder — including the
   hidden `.github` folder (it holds the schedule).
3. Click **Commit changes**.

## Step 4 — Turn on the schedule (Actions)  *(I can drive this)*
1. Open the **Actions** tab.
2. If it asks, click **"I understand my workflows, enable them"**.
3. You'll see **"Update NRL tips"**. Click it → **Run workflow** once to test it now.

## Step 5 — Turn on the website (Pages)  *(I can drive this)*
1. **Settings** → **Pages**.
2. Under "Build and deployment", Source = **Deploy from a branch**.
3. Branch = **main**, folder = **/ (root)** → **Save**.
4. After a minute your link appears at the top of that page, like
   `https://YOURNAME.github.io/nrl-tipping/`.

## Done
Bookmark that link on your phone. From then on:
- Every morning/afternoon GitHub fetches the latest results and re-learns.
- You open the link and see who to tip — no logging, no laptop needed.

---

### Notes
- **Free:** public repos get unlimited free scheduling on GitHub.
- **First run:** the very first update may need one small tweak from me once we can
  see the real page output — that's expected, I'll sort it.
- **If it ever goes quiet:** GitHub pauses schedules after 60 days of no activity, but
  the daily auto-updates keep it awake through the season.
