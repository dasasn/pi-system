# ~/.agent-rules — aturan operator & skill

Sumber tunggal aturan dan skill untuk semua agent di mesin ini.

## Isi
| Path | Fungsi |
| --- | --- |
| `operator.AGENTS.md.master` | master aturan operator (read-only) |
| `skills/` | master seluruh skill (35 entri) |
| `rules-guard.sh` | penjaga: pulihkan aturan + symlink tiap 60 detik |
| `guard.log` | catatan setiap pemulihan |
| `*.bak` | backup kondisi awal instabox |

## Peta symlink (jangan diganti dengan file biasa)
- `~/AGENTS.md` → file nyata (perm 444)
- `~/.codex/AGENTS.md` → `~/AGENTS.md`
- `~/.claude/CLAUDE.md` → `~/AGENTS.md`
- `~/.claude/skills`, `~/.agents/skills`, `~/.pi/agent/skills`,
  `~/.free-pi/agent/skills`, `~/.config/opencode/skill_h` → `~/.agent-rules/skills`

## Ubah aturan
1. Edit `~/.agent-rules/operator.AGENTS.md.master`
2. `cp ~/.agent-rules/operator.AGENTS.md.master ~/AGENTS.md && chmod 444 ~/AGENTS.md`
3. Guard otomatis menyelaraskan hash pada tick berikutnya.

## Tambah skill
Taruh di `~/.agent-rules/skills/<nama>/SKILL.md`. Semua model langsung melihatnya.

## Kalau ada yang rusak
```bash
bash ~/.agent-rules/rules-guard.sh
cat ~/.agent-rules/guard.log
```
Timer: `systemctl --user status rules-guard.timer`
