# OpenCode GitHub Integration

How the OpenCode agent is wired into this repository through GitHub Actions,
what it needs to run, and how to diagnose it when it misbehaves.

`AGENTS.md` says project documentation lives in `planning/`. This file is the
one deliberate exception: it documents `.github/workflows/`, so keeping it beside
the workflows means a change to a workflow and the change to its documentation
land in the same directory, in the same review.

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

1. The repository owner (`paziyax`) comments `/oc` (or `/opencode`) followed by
   an instruction, on an issue or a pull request. The workflow's `if` condition
   checks `github.event.comment.user.login`, so a comment from anyone else skips
   the job entirely: no runner, no model call, no cost.
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
| `opencode.yml` | `issue_comment`, `pull_request_review_comment`; needs a `/oc` or `/opencode` prefix **and** the commenter to be the repository owner | app mode | `id-token: write`, `contents: read` |
| `opencode-review.yml` | `pull_request` on `opened`, `synchronize`, `reopened`, `ready_for_review` | `GITHUB_TOKEN` | `contents: read`, `pull-requests: write`, `issues: write` |

## Required setup

- OpenCode GitHub App installed on this repository
- Repository secret `OPENROUTER_API_KEY`
- Permissions exactly as listed in the table above
- Model: `openrouter/deepseek/deepseek-v4.1-flash-1017`

## Things that surprise people

- Two versions float independently of this repository. The action reference is
  `@latest`, and the action itself downloads the CLI from
  `https://opencode.ai/install` on every run, so neither is tied to a commit
  here. Your local CLI can be a different major line from the one CI runs. Use
  `opencode --version` locally and read the version printed in the run log to
  compare.
- Setup is manual: install the app, add the secret, commit the workflow files.
  Newer CLI releases dropped the `opencode github install` helper command, so do
  not expect a guided wizard.
- The workflow installs no plugin dependencies. The runner loads whatever the CLI
  finds in the repository, so a plugin that needs npm packages must have them
  installed by a workflow step; otherwise it works locally and fails in CI.
- Pull requests from forks are not given secrets. The workflow still runs, but
  `OPENROUTER_API_KEY` is empty, so the run fails at auth rather than reviewing.
  Treat fork pull requests as unreviewed and read them yourself.
- Draft pull requests are skipped explicitly. `opened` and `synchronize` fire for
  drafts too, so `opencode-review.yml` guards its job with
  `if: github.event.pull_request.draft == false`.
- `issues: write` alone is not enough for the review workflow to comment on a pull
  request. It needs `pull-requests: write` as well, otherwise the comment request
  returns `403 Resource not accessible by integration`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The run never starts | The comment came from an account other than `paziyax`, the body does not start with `/oc` or `/opencode`, or the workflow is not on the default branch | Comment from the owner account, begin the comment with the trigger phrase, and confirm the workflow exists on the default branch |
| `User <bot> does not have write permissions` | The event's actor has no write access, typically a PR opened by the bot on a `pull_request` event | Use `GITHUB_TOKEN` mode (`use_github_token: true`) for that workflow |
| `403 Resource not accessible by integration` on issue comments or reactions | The job that posts the comment is missing `issues: write` or `pull-requests: write` | Add both to that job's `permissions`; `opencode.yml` does not need them because it uses the app token instead |
| The run fails fast with an auth error | The app is not installed on this repository, or `OPENROUTER_API_KEY` is unset or misnamed | Install the app on this repository and add the secret under the exact name |
| The run succeeds but no comment is posted | The instruction was ambiguous, or the model had nothing to add | Make the instruction explicit, and read the run log for the model's output |
