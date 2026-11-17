# OpenCode GitHub Integration

This document explains how the OpenCode agent is wired into this repository through GitHub Actions, what it needs to run, and how to diagnose it when it misbehaves.

## What it is

The OpenCode GitHub App (github.com/apps/opencode-agent) is a GitHub App, not a personal access token. It lets a workflow obtain a short-lived token scoped to this one repository, so no long-lived credential is stored anywhere.

## How it works

1. A user comments `/oc` followed by an instruction on an issue or pull request.
2. GitHub Actions starts the opencode workflow.
3. `actions/checkout` clones the repository; `persist-credentials` is `false` so the default token is never written into git config.
4. The runner requests an OIDC token via `id-token: write`.
5. That token is exchanged at `api.opencode.ai` for an installation token.
6. The app checks that it is installed on this repository, then returns a token with write access.
7. OpenCode reads `AGENTS.md` and `.opencode/opencode.json`, runs the task, and posts comments or pushes commits as needed.

## The two workflows in this repository

| Workflow | Trigger | Purpose |
|---|---|---|
| `.github/workflows/opencode.yml` | `issue_comment`, `pull_request_review_comment`, gated on `/oc` or `/opencode` | Runs an on-demand task from a user instruction |
| `.github/workflows/opencode-review.yml` | `pull_request` on `opened`, `synchronize`, `reopened`, `ready_for_review` | Runs an automatic review of the pull request |

## Required setup

- App installed on this repository only
- Repository secret `OPENROUTER_API_KEY`
- Permissions `id-token: write` and `contents: read`
- Model: `openrouter/deepseek/deepseek-v4.1-flash-1017`

## Things that surprise people

- CI runs OpenCode V1.19.6 even though local development uses V2, because the action installs whatever `releases/latest` points to, which is still the V1 line.
- V2 removed the `opencode github install` setup command, so setup is manual.
- V2 plugins do not load in CI; only config, `AGENTS.md` and workflow inputs apply.
- Pull requests from forks are not given secrets, so the review workflow stays silent on outside contributions.
- `share: false` keeps sessions private on this public repository.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The run never starts | The comment did not contain `/oc` or `/opencode`, or the workflow file is not on the default branch | Include the trigger phrase in the comment and confirm the workflow exists on the default branch |
| The run fails fast with an auth error | The app is not installed on this repository, OIDC permissions are missing, or `OPENROUTER_API_KEY` is unset | Install the app on this repository, grant `id-token: write`, and add the `OPENROUTER_API_KEY` secret |
| The run succeeds but no comment is posted | OpenCode had nothing to report, the instruction was ambiguous, or the job is blocked from writing | Make the instruction explicit and check the workflow permissions and repository settings |
