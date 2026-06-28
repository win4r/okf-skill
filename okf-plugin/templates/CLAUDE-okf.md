<!-- Paste this block into your project's CLAUDE.md to opt into OKF soft-mode upkeep.
     The plugin ships NO hooks by design (it stays side-effect-free); this snippet is how you
     turn on automatic consume/maintain behavior for a repo that contains an OKF bundle. -->

## OKF bundle

This repo contains an Open Knowledge Format bundle at `<path-to-bundle>/`.

- Before answering questions about the domain it documents, read that bundle's root `index.md`
  first, or run `okf context <bundle> "<topic>"` — do NOT read every file.
- After making a durable change to the domain, update the affected concept(s): edit the body,
  bump `timestamp`, regenerate indexes (`okf index <bundle> --recursive --write`), and append a
  dated entry to `log.md`.
- Treat broken cross-links as not-yet-written knowledge, not errors.
- Before committing changes to the bundle, run `okf validate <bundle>` and fix every error.
