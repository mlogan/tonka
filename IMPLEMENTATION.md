# Rust sccache in the VM — implementation notes

Branch: `mlogan-sccache`

## Design
- `guest/rust-setup.sh` (idempotent) installs sccache, writes `~/.cargo/config.toml`
  (`rustc-wrapper`, `build.incremental = false`) and sccache's config file (disk cache dir and size cap),
  and installs a daily cron job that wipes the cache when the data volume is >= 85% full.
- `setup_rust` in `tonka` runs from `ensure_vm` when `rust` is in `TONKA_TOOLS`. It is gated on an
  md5 of the script plus `TONKA_SCCACHE_SIZE`, stored in the VM at `~/.tonka/rust-setup.md5`.

## Done
- Script, host hook, `TONKA_SCCACHE_SIZE` config (default 200G), README/TONKA_FOR_DUMMIES docs.
- Tested in the VM: config written, second bring-up skips setup, gc script runs, and two separate
  projects depending on serde share cache hits (6 hits on the second build); no `incremental/` dir.

## Remaining
- Workspace crates miss the cache across worktrees because their paths differ; only
  dependencies are shared.
- Existing `target/*/incremental` dirs in VM projects are not removed.
