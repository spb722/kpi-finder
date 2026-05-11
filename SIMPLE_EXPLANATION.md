# KPI Finder — Plain English Explanation

---

## What Does This System Do?

Imagine you work in a telecom company and you want to run a **marketing campaign**. You want to target a specific group of customers — say, *"customers from India"* or *"customers who recharged more than 5 OMR last month."*

The problem: your database doesn't understand plain English. It stores data in columns with technical names like `Profile_Cdr_Nationality` or `Recharge_Seg_Fct_Amount`. Someone has to translate your plain English condition into the exact database column the system needs to use.

**KPI Finder does that translation automatically.**

You type a condition in plain English → it finds the exact database column (called a KPI or feature) that represents it.

---

## A Simple Analogy

Think of it like a **smart hotel concierge** at a giant hotel with thousands of rooms and services.

You walk up and say: *"I'd like a room with an ocean view, close to the pool."*

The concierge doesn't hand you a 500-page room catalog. They already know the hotel inside-out. They check a few places they know are likely (their best guesses), confirm the right room, and hand you the key.

KPI Finder is that concierge — but for telecom database columns.

---

## The Full Example

**You send in:**
```
"customer is from India"
```

**It returns:**
```
Database Table : Profile_Cdr_group
Column Name    : Profile_Cdr_Nationality
Match Type     : equals
Value          : India
Confidence     : 96%
Reason         : "The condition asks for the customer's registered nationality."
```

Now your campaign system knows exactly which column to look up and what value to filter on.

---

## How It Works — Step by Step

The system searches in **three layers**, in a fixed priority order. It tries the highest-priority layer first. If nothing matches, it moves to the next.

```
Layer 1: Virtual Profiles       (special pre-built bundles)
    ↓ not found
Layer 2: Customer 360           (ready-made summary KPIs)
    ↓ not found
Layer 3: Normal KPI Groups      (the full database of raw features)
    ↓ still not found
Result: Unmatched
```

Think of these layers like shelves in a library — you check the "quick reference" shelf first, then "popular books," then the full archives.

---

## All the Scenarios

### Scenario 1 — Virtual Profile Match (fastest path)

**What it is:** Sometimes a condition has already been pre-packaged by the business team into a "Virtual Profile." For example, a profile called *"High Value Expat"* might already bundle together nationality + spending + usage rules.

**What happens:**
- System searches the Virtual Profile library.
- An AI judge reads the top matches and decides: *"Yes, this condition is exactly what this virtual profile represents."*
- Done. Returns the virtual profile name immediately.

**Example:**
```
Input:    "high-spending expat customer"
Output:   Virtual Profile → "High_Value_Expat_Profile"
```

**Why it's the priority:** Virtual profiles are business-created shortcuts. If one exists, it's more accurate than building the logic from scratch.

---

### Scenario 2 — Customer 360 Match

**What it is:** The company pre-computes many common KPIs about each customer (like "did this customer call India in the last 30 days?"). These live in a special "360 Profile" table.

**What happens:**
- Virtual profile search found nothing useful.
- System searches the Customer 360 database.
- AI judge reads the candidates and decides if any directly match.

**Example:**
```
Input:    "customer called internationally in last 30 days"
Output:   Customer 360 → "CUST_360_IDD_CALLING_FLAG_30D"
```

**Important nuance:** The AI judge is careful here. If you ask *"customer is from India,"* it will **not** accept `CUST_360_IDD_INDIA_CALLING_FLAG_30D` (which means "called India"), because that's a different thing entirely.

---

### Scenario 3 — Normal KPI Group Match (first try succeeds)

**What it is:** The largest and most detailed layer — hundreds of raw database columns organized into groups (tables). Examples of groups: `Profile_Cdr_group`, `Recharge_Seg_Fct`, `LIFECYCLE_CDR`, `Common_Seg_Fct`.

**What happens (4 sub-steps):**

1. **Find the right group:** The system searches a "group routing" index to figure out which table is most likely to contain the answer. For *"customer is from India,"* it correctly finds `Profile_Cdr_group` (the profile/demographic table).

2. **Translate the condition:** An AI rewrites the plain-English condition into a precise search phrase. *"customer is from India"* becomes *"subscriber registered nationality country India."* This makes the next search much more accurate.

3. **Search inside the group:** The system searches inside `Profile_Cdr_group` using that precise phrase, and finds candidate columns like `Profile_Cdr_Nationality`, `Dealer`, `Business`, etc.

4. **Validate the best match:** A final AI judge reviews the top candidates and confirms which one actually represents the condition. It picks `Profile_Cdr_Nationality` and explains why.

**Example:**
```
Input:    "customer is from India"
Group:    Profile_Cdr_group       ← step 1: routing
Search:   "subscriber registered nationality country India"  ← step 2: translation
Columns:  Profile_Cdr_Nationality, Dealer, Business...      ← step 3: candidates
Output:   Profile_Cdr_Nationality = "India"                 ← step 4: confirmed
```

---

### Scenario 4 — Normal KPI Group Match (fallback — second group tried)

**What it is:** Sometimes the first group doesn't have the right column. The system tries the next best group automatically.

**What happens:**
- Steps 1–4 above run for the first group. AI judge says: *"No, none of these columns match the condition."*
- System picks the second-ranked group and repeats steps 2–4.
- This can happen up to **3 times** (configurable). If the 3rd attempt also fails, it gives up.

**Example:**
```
Input:     "customer received a bonus in last 7 days"
Group 1:   Common_Seg_Fct → no match found
Group 2:   LIFECYCLE_CDR  → match found: "Bonus_Received_Flag_7D"
Output:    LIFECYCLE_CDR, Bonus_Received_Flag_7D
```

**Why this matters:** Not every condition fits neatly into the top-ranked group. The fallback loop makes the system resilient without needing a human to intervene.

---

### Scenario 5 — No Match Found (Unmatched)

**What it is:** After trying all three layers and up to 3 groups in the normal path, the system still can't find a column that represents the condition.

**What happens:**
- System returns the condition as "unmatched" with a reason.
- The overall response includes a `mismatch_percentage` showing how many of the input conditions could not be resolved.

**Example:**
```
Input:     "customer owns a pet"
Output:    Unmatched — "No KPI found after virtual profile, 360, and top normal groups."
```

This is honest feedback to the campaign team: *"We don't have data for this condition in our database."*

---

### Scenario 6 — Multiple Conditions at Once

**What it is:** A campaign usually has more than one condition. You can send all of them in a single request.

**What happens:**
- Each condition is processed independently through the same flow above.
- Results are collected and returned together.
- The response shows which conditions matched, which didn't, and a mismatch percentage.

**Example:**
```
Input:
  - "customer is from India"
  - "customer recharged more than 5 OMR"
  - "customer has active data plan"

Output:
  Matched:
    - "customer is from India"       → Profile_Cdr_Nationality = India
    - "customer recharged > 5 OMR"  → Recharge_Seg_Fct_Amount > 5
  Unmatched:
    - "customer has active data plan" → no KPI found
  Mismatch: 33%
```

---

## Summary Table

| Scenario | What Happens | How Fast |
|---|---|---|
| Virtual Profile found | Returns the pre-built profile name | Fastest |
| Customer 360 found | Returns the pre-computed KPI | Fast |
| Normal group, first try works | Routes to group → translates → searches → validates | Moderate |
| Normal group, needs fallback | Retries up to 3 groups before giving up | Slower |
| No match at all | Returns "unmatched" with a reason | — |
| Multiple conditions | Each condition goes through the flow independently | Scales linearly |

---

## What the System Does NOT Do

- It does **not** run the actual campaign. It only tells you which database column to use.
- It does **not** create new KPIs or columns. It only finds what already exists.
- It does **not** guarantee a match if the data simply doesn't exist in the database.

---

## Key Terms Glossary

| Term | Plain English Meaning |
|---|---|
| **KPI / Feature** | A database column that stores one piece of information about a customer |
| **Group / Table** | A collection of related columns (e.g., all columns about recharges) |
| **Virtual Profile** | A pre-built, named condition bundle created by the business team |
| **Customer 360** | A table of pre-computed summary metrics about each customer |
| **Condition** | A plain-English rule like "customer is from India" |
| **Matched** | A database column was found that represents the condition |
| **Unmatched** | No suitable database column could be found |
| **Confidence** | How sure the system is about the match (0–100%) |
