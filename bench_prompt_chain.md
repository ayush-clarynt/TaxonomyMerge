# Outlet-Format Mapping Bench — prompt to use

Paste the prompt below into a **normal Claude chat**. Claude will write a refined,
detailed prompt for you to paste into **Claude Cowork**, which then builds the tool and
pushes it to git.

---

## Prompt — paste into normal Claude chat

```
I use two Claude products: you (regular Claude) and Claude Cowork (an agent that can
read/write files in a folder and run git).

Don't build anything yourself. Instead, write a single, refined, copy-paste-ready prompt
that I'll give to Claude Cowork. Return only that prompt, in one code block.

Here's what the Cowork prompt should make Cowork do:

- Build a single, self-contained HTML page (a small "mapping bench") that runs entirely
  in the browser.
- I upload two files: a CSV of place types (it has a `place_type` column plus a few other
  columns) and a taxonomy JSON that lists the outlet_format codes and their meanings.
- For each place_type, the page assigns the best outlet_format from the taxonomy — but
  only for places that are an actual point of sale (a shop/outlet that sells goods, plus
  eateries and salons). Anything that isn't a point of sale (clinics, banks, schools,
  offices, transport, etc.) should be left blank.
- It shows the results in a table and lets me download a CSV that is my original file
  plus the new outlet_format column (and a short reason for each mapping).
- Then commit and push the HTML file to git.

Feel free to fill in sensible details and ask me for anything you need (like the git repo).
```

---

Tip: if Claude's generated Cowork prompt looks good, paste it straight into Cowork. If you
want it to reproduce the exact mapping rules we built here, also attach this folder's
taxonomy JSON and the `map_outlet_format.py` script when you run the Cowork prompt.
