# Homelab fork

Branch `homelab` (the default branch) = an upstream release of
[jekalmin/extended_openai_conversation](https://github.com/jekalmin/extended_openai_conversation)
plus the changes below. Echo Experience needs them: its `echo_*` tools reach the
model through Home Assistant's LLM API.

## Carried changes

1. **Upstream PR [#446](https://github.com/jekalmin/extended_openai_conversation/pull/446)**
   (simcop2387, branch `feature/hass-llm-api-integrations`) — built-in HA LLM API tool access.
   Not merged upstream yet. Merged here at `2148ba8`.
2. **PR #446 on HA 2026.10** — its `llm_api` tool path unwraps `llm.ToolResult` and builds the
   result with `_make_tool_result_content`.
3. **Unconvertible tool schemas (HA 2026.9+)** — use probatio's converter when present; schema
   helpers skip non-dict fragments; a tool whose parameters can't be converted gets an empty
   schema instead of breaking every request.

Guarded by `tests/test_homelab_llm_api.py`.

## Staying current

`.github/workflows/upstream-sync.yml` runs weekly (Mon 06:17 UTC, or by hand):

- newest upstream release merges cleanly → branch `sync/<tag>`, a PR into `homelab`, CI dispatched on it;
- merge conflicts → an issue listing the files;
- PR #446 gets new commits or is merged → an issue.

Manual merge:

```bash
git fetch upstream --tags
git switch homelab && git merge <tag>
# resolve, keep the changes above, then:
git push origin homelab
```

Upstream `develop` is ahead of releases; we follow releases only.
