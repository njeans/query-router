# Query Router - 1 Minute Demo Script

**Setup:** Open browser to `http://localhost:8000/ui`. Select "Cofounder IP theft" from the dropdown.

---

**[0:00 - 0:10] The Problem**

> "Imagine you need legal advice about your cofounder threatening to leave with your source code. You want to use an AI — but the query contains your company name, your role, and sensitive business details. How do you get a good answer without exposing all of that to a third-party provider?"

Click **Run Pipeline**.

**[0:10 - 0:20] Sanitize** (Tinfoil badge)

> "Step one: we detect every sensitive entity — names, companies, job titles — and replace them with typed placeholders. This runs inside a Tinfoil secure enclave, so even the inference provider can't see your data. The original values never leave the enclave."

Point to the placeholder map showing the substitutions.

**[0:20 - 0:30] Decompose + Leak Check** (Tinfoil badges)

> "Next, still inside Tinfoil, the sanitized query is split into generic, self-contained sub-questions. Then each fragment passes a deterministic leak check — pattern matching, PII detection, value matching — to verify nothing identifying survived."

Point to the green "Safe" labels on both fragments.

**[0:30 - 0:40] Confirm**

> "Before anything leaves your machine, you get to review exactly what will be sent. These are the only things the outside provider will ever see."

Click **Approve & Send**.

**[0:40 - 0:50] Remote Send** (Darkbloom badge)

> "Each fragment goes to Darkbloom as a separate, unlinkable request — different timing, no shared session. Darkbloom sees two generic legal questions. They have no way to connect them or trace them back to you."

Point to the sent/response pairs.

**[0:50 - 1:00] Recombine** (Tinfoil badge)

> "Finally, back inside Tinfoil's enclave, the answers are merged and the placeholders are swapped back in. You get a complete, personalized answer — but no single external provider ever saw the full picture."

Point to the final answer with real names restored.

---

**Key line if you have 5 extra seconds:**

> "Tinfoil handles everything sensitive. Darkbloom only ever sees generic questions. That's the split."
