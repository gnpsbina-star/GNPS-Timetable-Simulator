# Archive

Files kept for reference only. Nothing in the live app links to or runs them.

- `migrations/` holds one-off scripts that applied specific timetable edits to the 2026-27 data (Class 10 period swaps, Drawing conversions). They look for data files in their own folder, so running them from here will not touch the live `timetable.sqlite` or JSON files. Do not move them back to rerun them.
- `prototypes/` holds early HTML previews of modules that have since been built into the main pages (`index.html`, `substitution.html`, `prerequisites.html`, `creator.html`).
