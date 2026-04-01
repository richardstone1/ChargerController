# Contributing to ChargerController

This project is **open source** under the [MIT License](LICENSE). We welcome issues, ideas, documentation improvements, and pull requests.

## Ground rules

- Be respectful and constructive. Assume good intent.
- Prefer small, focused changes that are easy to review.
- For hardware-related changes, describe wiring or pin assumptions in the PR.
- **Preserve attribution**: do not remove copyright or license notices from files that include third-party code (see `CREDITS.md`).

## OBI / protocol changes

Changes that touch `obi.py` or Makita LXT behavior should stay compatible with the **Open Battery Information** protocol expectations where practical, and should note any intentional deviations in the PR.

## How to submit a change

1. Fork the repository (or ask for collaborator access if you’re working with the maintainer).
2. Create a branch for your work.
3. Test on real hardware when possible (Pico W + your bench setup).
4. Open a pull request with a short description of **what** changed and **why**.

## Security and secrets

Do **not** commit Wi‑Fi passwords, API keys, or personal data. Use local `secrets` files (gitignored) or environment-specific config.
