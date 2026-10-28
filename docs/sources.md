# Source compliance review

Checked on 2026-10-28 with the user agent `Lakshya/0.1 (+https://github.com/Shubham-0102; yadavvshubham0102@gmail.com)`, at least 5 seconds between requests to the same site (25 requests in total across 6 sites).

**Decision rule**
- **Allowed:** robots.txt allows the job pages and the terms of service do not forbid automated access or reuse.
- **Blocked:** the terms forbid it. We ask for permission or a feed instead.
- **Unclear:** treated as blocked.

robots.txt only tells crawlers which paths they may fetch. The terms of service decide what we may do with the content, so the stricter of the two wins.

This is a reading of what each site publishes, not legal advice. Terms change: re-check before adding a source, and whenever a site asks us to stop.

## Summary

| Source | robots.txt | Terms of service | Verdict |
| --- | --- | --- | --- |
| jobsnepal.com | Allows everything | None published (not linked anywhere; `/terms*` and `/privacy-policy` return 404; nothing in the FAQ) | **Allowed** |
| merojob.com | Allows everything; `Content-Signal: search=yes, ai-input=yes, ai-train=no` | Forbids scraping and copying listings for third-party platforms | **Blocked** |
| kumarijob.com | Allows job pages (blocks `/api/`, `/jobseeker*`, admin, login) | Personal, non-commercial use only; one copy for personal use | **Blocked** |
| kantipurjob.com | Allows everything | Personal, non-commercial use only; no republication; no deep links | **Blocked** |
| ramrojob.com | Allows everything | No copying or reuse without written consent | **Blocked** |
| hamrojob.com | Allows everything (also points to `/llms.txt`) | Not checked: the homepage redirects to `/lander`, which looks like a parked domain rather than a job portal | **Not a source** |

## jobsnepal.com: allowed

- **robots.txt:** `User-agent: *` / `Disallow:` (empty, so everything is allowed). No `Crawl-delay`, so we use our default 5 s.
- **Terms:** none published. The footer only says "© 2000 - 2026 JobsNepal Pvt. Ltd. All Right Reserved." Because the content is still copyrighted, we follow the plan's display rule: show a short summary and send users to the original posting to apply.
- **Contact:** info@jobsnepal.com. Send a courtesy email (template below) so they can object if they want.
- **Technical notes:**
  - Server-rendered: job links and details are in the plain HTML, so no JavaScript is needed.
  - No JSON-LD `JobPosting` (the homepage only has `Organization`), so we use CSS selectors.
  - Listing: `https://www.jobsnepal.com/jobs?page=N`, 12 jobs per page, "Showing 1 to 12 of 156 results" (13 pages).
  - Detail: `https://www.jobsnepal.com/<slug>-<id>`, e.g. `/adminfinance-coordinator-144747`. The trailing number is the `external_id`.
  - Structured fields on the detail page: title, company, "Job posted on 28 Oct, 2026", "Apply before 18 Nov, 2026". Location, experience and salary are usually only in the free-text description (e.g. "Duty Station: … Kathmandu", "Minimum of 5 years of experience"). That is why Phase 2 adds AI extraction.
  - The listings include non-job notices: "Call for Bid", "Expression of Interest (EOI)", "Terms of Reference (ToR)". The cleaning step needs to flag or filter these.
  - First full run: about 13 listing pages + 156 detail pages ≈ 170 requests ≈ 15 minutes at 5 s each. Later runs only fetch detail pages for new jobs.
  - Test fixtures: jobsnepal pages are copyrighted, so committed fixtures should be trimmed to the parts the parser needs, not full pages, if the repo is public.

## merojob.com: blocked

- **robots.txt:** allows everything, and declares Cloudflare content signals `search=yes, ai-input=yes, ai-train=no`.
- **Terms** (`/terms-and-conditions`), under "this license does not allow":
  > Any commercial exploitation of the website content (e.g., selling access to job listings or copying data for third-party platforms).
  > Data scraping, automated bots, or other tools for collecting or mining personal or professional data.

  and:
  > All content on Merojob including logos, page layouts, text, graphics, software, and job listings are the intellectual property of Merojob Ltd. or its licensed partners and are protected under copyright and trademark laws.
- **Why blocked:** the terms explicitly forbid scraping and reuse on other platforms, even though robots.txt allows crawling.
- **Contact:** info@merojob.com

## kumarijob.com: blocked

- **robots.txt:** job pages (`/<company-slug>/<id>-<title-slug>`) are allowed; `/api/`, `/jobseeker*`, `/kumari-job/`, admin and login paths are blocked.
- **Terms** (`/terms-condition`), for job seekers:
  > As a job seeker, you are given limited and non-exclusive access to use the Kumari Job website only for personal and non-commercial purposes.
  > You may view and download one copy of the content for personal use.
- **Why blocked:** there is no explicit scraping clause, but the license only covers personal use. Collecting listings and showing them to other users goes beyond that.
- **Contact:** info@kumarijob.com

## kantipurjob.com: blocked

- **robots.txt:** allows everything.
- **Terms** (`/terms`), section 1:
  > The Website and the Services are for personal and non-commercial use only. […] you may not use any information from any directory or other listing or information retrieval service […] in connection with any business or commercial undertaking (whether or not for profit). Any other use of materials on the Website and/or the Services (including without limitation reproduction for a purpose other than that noted above and any modification, distribution or republication) without the prior written permission of kantipurjob.com is strictly prohibited. You also agree not to deep-link and/or frame the Website or any of the Services for any purpose, unless specifically authorised by kantipurjob.com to do so.
- **Why blocked:** it forbids republication, including not-for-profit use, and even deep links to postings, which is how we send users back to the source.
- **Contact:** info@kantipurjob.com

## ramrojob.com: blocked

- **robots.txt:** allows everything.
- **Terms** (`/terms-conditions`), section 4:
  > No content may be copied, redistributed, or reused without prior written consent.
- **Contact:** no email published; use the contact form on the site.

## Permission request template

The project owner sends these; nothing is sent automatically. Send to the blocked portals to ask for permission or a feed, and to jobsnepal as a courtesy.

> **Subject:** Permission request: listing your jobs in a student job-search project
>
> Hello,
>
> I'm Shubham Yadav, a computer science and AI student. I'm building Lakshya, a free, non-commercial job-search assistant that helps students find jobs that match their CV (https://github.com/Shubham-0102).
>
> I would like to include jobs from {SITE} in it. I would only show each job's title, company, deadline and a short summary, always with a link back to the original posting on {SITE}, where users would read the full post and apply. So it would send traffic to your site rather than replace it.
>
> If you allow it, the collector would identify itself honestly ("Lakshya/0.1"), make at most one request every 5 seconds, run twice a day, and stop immediately if you ask. If you offer a feed or API, I would much rather use that.
>
> Would you be willing to give permission, or point me to the right person?
>
> Thank you,
> Shubham Yadav
> yadavvshubham0102@gmail.com
