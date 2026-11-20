# Rust compiler cache (kache) in the VM — implementation notes

Branch: `mlogan-kache` (replaces the sccache setup from `mlogan-sccache`)

## Design
- `guest/rust-setup.sh` (idempotent) installs kache from the `kunobi-ninja/kunobi` tap and writes
  `~/.cargo/config.toml` (`rustc-wrapper`) and `~/.config/kache/config.toml` (store dir, size cap).
  It installs a daily cron job that runs `kache clean --cache --yes` when the data volume is >= 85% full.
- `kache init` is not used: it edits shell rc files, installs C/C++ shims, and adds a launchd service.
  The daemon starts on the first compile without the service.
- The script deletes the old sccache cache, config, and gc cron job.
- `setup_rust` in `tonka` is gated on an md5 of the script plus `TONKA_KACHE_SIZE`.

## Done
- Verified in the VM that kache shares workspace-crate hits across two checkouts at different
  absolute paths (`local_hit` for the workspace crate). sccache missed 4 units in the same test.
- Ran the script twice in the VM with a temporary HOME and a stub crontab: configs, cron line,
  and sccache cleanup are correct, and a cargo build went through kache.

## Remaining
- The live VM still uses sccache. The next `tonka` bring-up after merge applies the change.
- `~/.tonka.conf` users who set `TONKA_SCCACHE_SIZE` must rename it to `TONKA_KACHE_SIZE`.
