# Tonka Implementation Progress

## Status: In Progress

## Phase 1: Core Infrastructure

- [x] Create `tonka` CLI script (main entry point)
- [x] Create `guest/install.sh` (base VM setup)
- [x] Create `guest/configure.sh` (project VM setup)
- [x] Dotfiles support via TONKA_DOTFILES_REPO environment variable

## Phase 2: Project Management

- [ ] Implement `tonka new <repo-path> [project-name]`
- [ ] Implement `tonka start/stop/delete <project>`
- [ ] Implement `tonka list`
- [ ] Implement `tonka shell/claude <project>`

## Phase 3: Polish

- [ ] GitHub token handling
- [ ] SSH key management

## Verification

- [ ] `tonka new ~/dev/some-repo test-project` - creates VM, clones repo
- [ ] `tonka shell test-project` - SSH in, verify repo is cloned, ssh-agent works
- [ ] `tonka claude test-project` - Claude starts in project directory
- [ ] `tonka stop test-project` - VM stops
- [ ] `tonka start test-project` - VM resumes
- [ ] `tonka delete test-project` - VM removed
