# Research Engine — Standing Ground Rules

1. One slice at a time. A slice is one branch, one report.
2. Test first. Every new rule has a failing test before the code that makes it pass.
3. The real UI path is the only path. The Run button and the tests call the same function.
4. Nothing on screen or in an export exists outside the ledger.
5. No claim of done without pasted evidence (command and output), never a summary of it.
6. If something in the brief is unclear or contradicts the code, stop and ask; do not guess.
7. Never commit *.db, outputs/, .env, denylist.txt or synthetic fixtures to real outputs. Stage files by name, never git add -A.

---

*Note: Refactor vs. rebuild is an architectural decision, not a standing rule.*
