# Business Statement — GSD Procurement Integrity Platform

## The problem

In April 2026, the Los Angeles City Controller's Fraud, Waste and Abuse
Unit published an investigative report finding that the General Services
Department (GSD) had paid a Gardena-based vendor, Makai Solutions,
**$460,972 for two hydraulic lifts that were never delivered**. The
report's findings, in sequence:

1. A GSD superintendent **verbally authorized an advance payment**,
   citing COVID-era supply chain urgency — in violation of City Charter
   rules that govern prepayments.
2. To trigger the payment in the City's financial system, staff were
   directed to **falsely mark the lifts as "received"** even though
   nothing had arrived.
3. The false receiving entry was entered under a **shared login**, so
   when investigators tried to determine who actually made the entry,
   it was, in their words, "almost impossible" to identify the individual.
4. The Controller's Office closed the case with two structural
   recommendations to GSD: (a) conduct periodic reviews of prepayment
   authorizations, and (b) train purchasing staff on the policy against
   shared logins.

This is not an isolated pattern. The same office's separate "On the
Lookout" Fraud, Waste and Abuse Annual Report documented $384,000+ in
electric vehicles that sat idle for two years at a different GSD-managed
yard because no department coordinated charging infrastructure before
deployment — a related but distinct failure of purchase-to-deployment
tracking. Both cases share a root cause: **GSD's procurement workflow has
no system-enforced link between "we said we'd pay," "we actually
received the goods," and "who is accountable for saying so."** Word
processors, verbal sign-offs, and shared system logins stand in for that
link today.

## The fix

The GSD Procurement Integrity Platform is a purchase-order and payment
workflow application that makes the Controller's own recommendations
structurally impossible to bypass, rather than relying on staff
remembering a policy:

- **No shared logins, ever.** Every account is individually authenticated
  and every write to the system — creating a PO, recording a delivery,
  requesting a payment, approving or releasing one — is permanently
  attributed to exactly one user id. "Almost impossible to determine who
  entered it" cannot happen here by construction.
- **Receiving requires evidence, not a checkbox.** A line item cannot be
  marked received without a serial/asset tag and a written evidence note,
  recorded by an authenticated Receiving Clerk. There is no way to mark
  goods "received" that were never delivered without leaving a specific,
  attributable, falsifiable record.
- **Prepayment is a documented, dual-approval path, not a verbal
  go-ahead.** A standard payment can only be requested once a PO's line
  items are fully received. If payment must precede delivery, the
  requester must supply a written justification, and release requires
  sign-off from **two different approval roles** (Superintendent and
  Finance) — one person's verbal authorization is structurally
  insufficient to move money.
- **Every vendor gets a transparent, rule-based risk score** — flagging
  high prepayment ratios, quantity mismatches between what was ordered
  and what was recorded as received, and any case where a segregation-of
  duties control was bypassed — so a pattern like the Makai Solutions
  case would surface to an auditor before a six-figure loss, not after.

## Value

**Quantitative:** the single case this project is modeled on cost the
City $460,972 in an unrecovered/at-risk payment for undelivered goods,
plus the DOT case cited above cost $384,000+ in idled capital assets.
Preventing one incident of this size over the life of the system pays
for the engineering effort many times over. Beyond loss prevention, an
individually-attributed audit trail collapses the investigative cost of
future incidents — the Controller's office in the real case spent staff
time trying to identify who made a shared-login entry; here that lookup
is a single query.

**Qualitative:** GSD gains a repeatable, demonstrable internal control
it can point to in future audits, rather than a training reminder about
policy. Superintendents and Finance approvers get a system that makes
the *compliant* path (justify, get two sign-offs, then release) no
slower than the shortcut that caused the real incident, which is what
makes a control durable in practice rather than just on paper.

## Source

City News Service / MyNewsLA, "Contractor for General Services Fails to
Deliver $461K Worth of Goods," April 2, 2026, reporting on the LA City
Controller's Office Fraud, Waste and Abuse Unit investigative report
into GSD vendor prepayments (Makai Solutions).
