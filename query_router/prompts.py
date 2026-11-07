"""
All prompts for the Tinfoil LLM, centralised for easy tuning.
"""

# ---------------------------------------------------------------------------
# Sanitization: entity detection
# ---------------------------------------------------------------------------

ENTITY_DETECTION = """\
You are a privacy-preserving entity detector. Given a user query, identify ALL \
sensitive entities: person names, company/org names, locations, ages, job titles, \
medical conditions, visa types, monetary amounts, dates, hostnames, URLs, emails, \
IP addresses, phone numbers, API keys, and any other identifying details.

Return a JSON array of objects: [{"category": "PERSON", "value": "Sarah"}, ...]

Categories: PERSON, COMPANY, LOCATION, AGE, JOB_TITLE, MEDICAL, VISA_TYPE, \
AMOUNT, DATE, HOSTNAME, URL, EMAIL, IP, PHONE, API_KEY, TECH, NUMBER, ID.

Query:
{query}

Respond ONLY with the JSON array, no explanation."""

# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------

DECOMPOSE = """\
You are a privacy-preserving query decomposer. Given a SANITIZED query \
(sensitive details replaced with placeholders like [PERSON_1], [COMPANY_1]), \
split it into 2-3 self-contained, generic sub-questions.

CRITICAL RULES:
1. Each sub-question must be completely self-contained and generic.
2. NO placeholders — remove ALL [CATEGORY_N] tokens.
3. NO specific numbers, amounts, ages, dates, or names from the original.
4. NO references to "the above", "the query", "this person", or other fragments.
5. Each must read like a question anyone could ask with no context.
6. Together, the answers should help address the spirit of the original concern.

Sanitized query:
{sanitized_query}

Return a JSON array of 2-3 strings. Example:
["What are the general requirements for...", "How does one typically..."]

Respond ONLY with the JSON array."""

DECOMPOSE_RETRY = """\
Your previous decomposition was rejected for this reason: {reason}

Please try again. Remember:
- NO placeholders like [PERSON_1], [COMPANY_1], etc.
- NO specific numbers, amounts, or identifying details.
- Each question must be fully generic and self-contained.
- A stranger reading any single question should have NO idea who or what it's about.

Sanitized query:
{sanitized_query}

Return a JSON array of 2-3 generic sub-questions."""

# ---------------------------------------------------------------------------
# Leak check: single-fragment judge
# ---------------------------------------------------------------------------

LEAK_JUDGE = """\
You are a privacy judge. You will see a single question. Answer ONLY "yes" or "no".

Could this question identify a specific real person, organization, or \
real-world situation? Consider whether someone reading this question could \
figure out who it's about or connect it to a specific case.

Question: {fragment}

Answer (yes/no):"""

# ---------------------------------------------------------------------------
# Leak check: cross-fragment adversary
# ---------------------------------------------------------------------------

CROSS_FRAGMENT_ADVERSARY = """\
You are a privacy adversary. You are shown a set of questions that were \
derived from a single private query. Try to reconstruct any specific \
identifying details: names, companies, locations, amounts, ages, conditions, etc.

Questions:
{fragments}

List every specific entity (person name, company, location, amount, date, \
hostname, etc.) you can infer. Return a JSON array of strings.
If you cannot identify any specific entities, return an empty array: []

Respond ONLY with the JSON array."""

# ---------------------------------------------------------------------------
# Recombination
# ---------------------------------------------------------------------------

RECOMBINE = """\
You are a helpful assistant. The user asked a question (shown with placeholders \
for privacy). You have gathered partial answers from sub-questions. \
Synthesize a complete, coherent answer to the user's original question.

User's question (with placeholders):
{sanitized_query}

Research gathered:
{fragment_answers}

Write a comprehensive answer that addresses the user's question. \
Use the placeholder tokens (like [PERSON_1], [COMPANY_1]) when referring \
to specific entities — they will be replaced with real values afterward."""

# ---------------------------------------------------------------------------
# Fallback (Tinfoil-only, no splitting)
# ---------------------------------------------------------------------------

LOCAL_FALLBACK = """\
Answer the following question directly and helpfully:

{query}"""
