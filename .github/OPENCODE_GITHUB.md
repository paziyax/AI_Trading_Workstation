# OpenCode GitHub Integration

How the OpenCode agent is wired into this repository through GitHub Actions,
what it needs to run, and how to diagnose it when it misbehaves.

This is infrastructure documentation, so it lives beside the workflows rather
than in `planning/`, which holds project specification and design documents.

## What it is

The OpenCode GitHub App (`github.com/apps/opencode-agent`) is a GitHub App, not a
personal access token. It lets a workflow obtain a short-lived token scoped to
this one repository, so no long-lived credential is stored anywhere.

## The two authentication modes

OpenCode can reach GitHub in either of two ways, and this repository uses both.

| Mode | Workflow input | Token source | Used by |
|---|---|---|---|
| App mode (OIDC) | none | OIDC token exchanged at `api.opencode.ai` for an installation token | `opencode.yml` |
| `GITHUB_TOKEN` mode | `use_github_token: true` | the workflow's own `GITHUB_TOKEN` | `opencode-review.yml` |

Why two: on `pull_request` events OpenCode checks whether the event's actor has
write access before doing anything. When the pull request was opened by the bot
itself, the actor is `opencode-agent[bot]`, which has no repository permission,
so app mode refuses to run. `GITHUB_TOKEN` mode skips that check and uses the
workflow's declared permissions instead.

## How the mention bot works

1. A user comments `/oc` (or `/opencode`) followed by an instruction, on an
   issue or a pull request.
2. GitHub Actions starts the `opencode` workflow.
3. `actions/checkout` clones the repository. `persist-credentials` is `false`, so
   the default token is never written into git config.
4. The runner requests an OIDC token, which requires `id-token: write`.
5. That token is exchanged at `api.opencode.ai` for an installation token.
6. The app confirms it is installed on this repository, then returns a token
   carrying the write access used for pushes and comments.
7. OpenCode reads `AGENTS.md` and `.opencode/opencode.json`, runs the task, then
   replies, pushes a branch, or opens a pull request as needed.

Pushes are possible even though the workflow declares only `contents: read`,
because the write access comes from the app token issued in step 6, not from
`GITHUB_TOKEN`.

## The two workflows

| Workflow | Trigger | Auth | Permissions |
|---|---|---|---|
| `opencode.yml` | `issue_comment`, `pull_request_review_comment`, gated on `/oc` or `/opencode` | app mode | `id-token: write`, `contents: read` |
| `opencode-review.yml` | `pull_request` on `opened`, `synchronize`, `reopened`, `ready_for_review` | `GITHUB_TOKEN` | `contents: read`, `pull-requests: write`, `issues: write` |

## Required setup

- OpenCode GitHub App installed on this repository
- Repository secret `OPENROUTER_API_KEY`
- Permissions exactly as listed in the table above
- Model: `openrouter/deepseek/deepseek-v4.1-flash-1017`
- `share: false` in both workflows, so sessions stay private on a public repository

## Things that surprise people

- CI runs OpenCode V1.19.6 even though local development uses V2. The action
  installs whatever `anomalyco/opencode` `releases/latest` points to, and at the
  time of writing that is still the V1 line. Check `releases/latest` rather than
  assuming this stays true.
- V2 removed the `opencode github install` setup command, so setup is manual: app,
  secret, workflow files.
- V2 plugins do not load in CI. Only `.opencode/opencode.json`, `AGENTS.md`, and
  the workflow inputs take effect.
- Pull requests from forks are not given secrets, so the review workflow stays
  silent on outside contributions.
- Draft pull requests are skipped until they are marked ready for review, because
  that is the trigger list in `opencode-review.yml`.
- `issues: write` alone is not enough for the review workflow to comment on a pull
  request. It needs `pull-requests: write` as well, otherwise the comment request
  returns `403 Resource not accessible by integration`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The run never starts | The comment did not contain `/oc` or `/opencode`, or the workflow is not on the default branch | Include the trigger phrase and confirm the workflow exists on the default branch |
| `User <bot> does not have write permissions` | The event's actor has no write access, typically a PR opened by the bot on a `pull_request` event | Use `GITHUB_TOKEN` mode (`use_github_token: true`) for that workflow |
| `403 Resource not accessible by integration` on issue comments or reactions | Missing `issues: write` or `pull-requests: write` in the job permissions | Grant both permissions as shown in the table above |
| The run fails fast with an auth error | The app is not installed on this repository, or `OPENROUTER_API_KEY` is unset or misnamed | Install the app on this repository and add the secret under the exact name |
| The run succeeds but no comment is posted | The instruction was ambiguous, or the model had nothing to add | Make the instruction explicit, and read the run log for the model's output |
