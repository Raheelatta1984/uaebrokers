# Live demo script — ReconIQ

**Purpose of the meeting:** not to sell software. To find out whether policy/premium/commission
reconciliation is painful enough that this broker would pay to make it go away, and to leave with
either a pilot offer or a clear "no".

**Length:** 20 minutes, of which no more than 6 are screen time.

---

## Before the call (2 minutes of prep)

```bash
./run.sh                 # or: ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Open `http://localhost:8000` in a clean browser window, zoomed to 100%.
- Click **Start over** so the first screen is empty.
- Keep `demo_data/` open in a file manager — dragging a real CSV in is more convincing than
  clicking a button, and it proves the tool is not a video.

If the machine or network fails: the whole thing runs locally, so there is nothing to reconnect.
If the browser fails, narrate the exception table from this repo's README — the numbers are fixed.

---

## Minute 0–2 — frame the problem, not the product

> "Before I show you anything — when the GIG or Orient statement lands each month, who actually
> opens it, and what happens next?"

Let them answer. Do not correct them. You are listening for:

- which files are involved (PDF? Excel? a portal export?)
- how many policies and how many insurers
- who does the work and how long it takes
- what happens when a commission is short — is it chased, or written off?

Only then open the app.

---

## Minute 2–3 — the screen no one has seen before

> "This is a prototype, not a product. It does one thing: it takes your policy register and any
> number of insurer statements, and it tells you every place the two disagree — priced, prioritised,
> with a next action attached."

Click **Load demo data**. Four files parse in about a second.

> "One broker register, three insurers, three different file formats — Excel, a normal PDF, and a
> PDF that has no table in it at all, just aligned text. That last one is the one that normally
> breaks these tools."

Point at the file rows and their confidence badges.

---

## Minute 3–5 — prove it is not a black box

On the **Confirm columns** screen:

> "It guessed the columns. Here is the mapping it chose, here is how confident it is, and here is
> the raw preview. If it guessed wrong, you fix it — it does not silently do something clever and
> hope you don't notice."

Change one mapping and change it back, to show it is live. Point at the tolerances:

> "These are the tolerance rules. AED 1? AED 50? Seven days or thirty? That is your policy, not
> my code — most tools bury this, and then finance doesn't trust the output."

Click **Run reconciliation**.

---

## Minute 5–9 — the result, narrated as their problem

The dashboard lands with 18 exceptions. Do not read all 18. Pick five, in this order:

1. **Cancelled but invoiced — `GIG/2026/000111`, AED 2,250.**
   > "The policy is cancelled in your book. The insurer is still paying commission on it. Some
   > brokers would call that a bonus. Your auditor will call it something else."
2. **Not in broker book — `GIG/2026/000199`, AED 2,800.**
   > "The insurer has paid on a policy your system does not have. Either a policy number was typed
   > wrong, or money is arriving for business you did not record."
3. **Not on insurer statement — `GIG/2026/000112`, AED 800 + `SKN/PRP/2026/7788`, AED 720.**
   > "This is the expensive direction. You wrote the business, you are owed the commission, and it
   > is simply not on the statement. Nobody notices unless someone reconciles line by line."
4. **Probable match — `OIC/MOT/2026/4508` vs `.../4580`.**
   > "One transposed digit. It did not silently merge them — it says 'I think these are the same
   > policy, confirm it'. That is the difference between a tool finance trusts and one they
   > switch off after a month."
5. **Duplicate on statement — `GIG/2026/000113`, AED 1,125.**
   > "The same policy twice. If this had been paid without checking, commission is out the door."

Then open one exception and let them read the side-by-side drawer themselves. Silence is fine here.

---

## Minute 9–11 — the export

Click **Export workbook**. Open the file.

> "Three sheets: the exception list with an action per line, a summary with every assumption
> stated, and the matched pairs so you can audit the matches as well as the exceptions. This is
> what your finance team would work from — not a dashboard they have to retype."

Say the assumption out loud before they find it:

> "The manual-effort number on that sheet is an assumption — 45 seconds a line. If your team takes
> two minutes a line, the saving is bigger. I would rather use your number than mine."

---

## Minute 11–16 — the questions that matter (stop presenting)

Ask, in order, and write down the answers:

1. "How close is this to what you do today — in file formats, and in the fields you compare?"
2. "Where would this have been wrong for your book?" *(Listen hard. There will be something:
   endorsements, credit notes, multi-currency, VAT handling, a custom class of business.)*
3. "How long does a monthly reconciliation take you now, and how many people?"
4. "When a commission is short by AED 200, what happens?"
5. "If I configured this against one month of your real statements — anonymised — would that be
   worth an hour of your team's time?"

If they lean in, propose the pilot scope explicitly:

> "One insurer, one month, your format. I configure it, run it alongside your current process, and
> we compare what each found. If it doesn't find anything your team didn't, you've lost an hour."

---

## Minute 16–20 — close

Ask for the decision, not the sale:

- **Pilot:** agree the insurer, the month, the contact and the file format on the call.
- **Not now:** ask what would have to be true. Then ask for one introduction to another broker
  where reconciliation is worse.

Do not promise: multi-tenancy, insurer API integrations, AI, real-time feeds, a mobile app, or
data residency guarantees that have not been checked.

---

## Questions you should expect, and honest answers

| Question | Answer |
|---|---|
| "Does this replace our broker management system?" | No. It sits on top of whatever produces your register and reads the insurers' statements. If your BMS already reconciles across all insurers in all formats, this is a smaller opportunity than I think — tell me. |
| "Does it read scanned PDFs?" | Not yet. It reads PDFs with real text, including ones with no table grid. Scans need OCR first, which is a separate build. |
| "Where does our data go?" | In this prototype, nowhere: it runs on this machine and holds files in memory only. What a real pilot needs — residency, retention, who can see commission data — is a conversation we should have before any real file is used. |
| "How accurate is the matching?" | Exact and normalised matches are deterministic. Anything with a typo is flagged as a probable match for a human to confirm — it never merges silently. In this demo: 34 matched, 1 of which needs confirming. |
| "Can it handle 5,000 policies a month?" | The prototype handles a few thousand lines in under a second. Volume is not the constraint; getting the mapping right for each insurer's format is. |
| "What would it cost?" | Not a question for today. The first step is a configured pilot on one insurer and one month — priced after we know the format. |

## What not to say

- Do not call it a platform, a SaaS product or AI. It is a reconciliation engine and a worksheet.
- Do not claim savings. The only measured numbers are the ones on screen, from synthetic data.
- Do not claim coverage of the broker's own process. It reconciles policies, premiums,
  commissions, dates and status. Claims, renewals workflow and document chasing are not built.
