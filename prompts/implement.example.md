# Implementation Stage

You are implementing the solution for **{{ issue.identifier }}**: {{ issue.title }}

**Current status:** {{ issue.state }}
**Labels:** {{ issue.labels }}
**URL:** {{ issue.url }}

## Issue description

{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

## Objective

**IMPORTANT: All Linear comments and workpad updates MUST be in Chinese (中文).**

Implement the solution, create a PR, and ensure it passes all quality checks.

## First run

1. Read the investigation summary from the Linear comments.
2. Read the relevant source files identified in the investigation.
3. Create a feature branch from `main`:
   ```
   git checkout -b {{ issue.identifier | lower }}-<short-description>
   ```
4. Implement the changes with clean, logical commits.
5. Run the full quality suite:
   - Type checking
   - Linting
   - All tests
6. Fix any failures before proceeding.
7. Push the branch and create a PR:
   ```
   git push -u origin HEAD
   gh pr create --title "{{ issue.identifier }}: <concise title>" --body "<description>"
   ```
8. Link the PR to the Linear issue.
9. Update the workpad with: what was done, what was tested, any known limitations.

## Rework run

If this is a rework run (a branch and PR already exist):

1. Find the existing PR:
   ```
   gh pr list --head <branch-name>
   ```
2. Read review comments and requested changes:
   ```
   gh pr view <number> --comments
   ```
3. Address each piece of feedback specifically.
4. Run the full quality suite again.
5. Push new commits to the existing branch (do not force-push).
6. Post a comment on the GitHub PR summarising the rework:
   - Which review comments were addressed
   - What was modified
   - Any decisions or trade-offs
7. Append a rework section to the Linear workpad.

## Completion protocol

When all work is done and the PR is ready for review:

1. **Post a final completion comment** to Linear with:
   - Summary of what was implemented
   - PR number and link
   - Branch name
   - Test results (pass/fail counts)
   - Any known limitations or follow-up items

2. **Move the Linear issue to "Human Review" state** to trigger the implementation review gate.

3. **STOP and EXIT immediately** after posting the completion comment. Do not:
   - Continue working on the issue
   - Add more comments
   - Check the PR status again
   - Wait for responses

Your session ends when the completion comment is posted. The human reviewer will take over from there.
