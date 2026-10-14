"""Skill match: how well a candidate fits a job order, as a % with the reasons.

Only what the job actually asks for is counted — a job with no skills listed is matched on the position,
experience and the other set requirements. Each point says ✓ or ✗ so the recruiter sees why.
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

STOP = {"and", "the", "for", "with", "of", "senior", "junior", "helper", "staff", "worker", "assistant"}


def words(text):
    return {w for w in re.findall(r"[a-z0-9+#]+", (text or "").lower()) if len(w) > 1 and w not in STOP}


def skill_list(text):
    return [s.strip() for s in re.split(r"[,;/\n]", text or "") if s.strip()]


def _has(skill, bag_text):
    """A job skill is found when all its words are in the candidate's trade / skills / notes."""
    need = words(skill)
    return bool(need) and need <= bag_text


def _age(born, today):
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def score(job, candidate, today=None):
    """(percent 0-100, [(ok, text)], blocked) — blocked when a must (gender) does not fit."""
    today = today or timezone.localdate()
    got = total = 0
    reasons = []
    blocked = False
    bag = words(f"{candidate.trade} {candidate.skills} {candidate.education}")

    pos = words(job.position)
    if pos:
        total += 30
        hit = pos & words(f"{candidate.trade} {candidate.skills}")
        part = len(hit) / len(pos)
        got += 30 * part
        reasons.append((part >= 0.5, candidate.trade or _("No position / skill")))

    needs = skill_list(job.skills)
    if needs:
        total += 30
        have = [s for s in needs if _has(s, bag)]
        got += 30 * len(have) / len(needs)
        for s in needs:
            reasons.append((s in have, s))

    if job.min_experience:
        total += 15
        yrs = candidate.experience_years or Decimal("0")
        got += 15 * min(1.0, float(yrs) / float(job.min_experience))
        reasons.append((yrs >= job.min_experience, _("%(have)s of %(need)s yrs experience") % {
            "have": f"{yrs:g}", "need": f"{job.min_experience:g}"}))

    if job.gender in ("male", "female"):
        total += 5
        if candidate.gender == job.gender:
            got += 5
            reasons.append((True, candidate.get_gender_display()))
        elif candidate.gender:
            blocked = True
            reasons.append((False, candidate.get_gender_display()))

    if job.nationality:
        total += 5
        ok = bool(words(job.nationality) & words(candidate.nationality))
        got += 5 if ok else 0
        reasons.append((ok, candidate.nationality or _("Nationality not given")))

    if job.max_age:
        total += 5
        if candidate.date_of_birth:
            age = _age(candidate.date_of_birth, today)
            ok = age <= job.max_age
            got += 5 if ok else 0
            reasons.append((ok, _("Age %(age)s") % {"age": age}))

    if job.salary and candidate.expected_salary:
        total += 5
        ok = candidate.expected_salary <= job.salary
        got += 5 if ok else 0
        reasons.append((ok, _("Expects %(amount)s") % {"amount": f"{candidate.expected_salary:,.0f}"}))

    total += 5
    if candidate.passport_expiry and candidate.passport_expiry >= today + timedelta(days=180):
        got += 5
        reasons.append((True, _("Passport valid")))
    elif candidate.passport_expiry:
        reasons.append((False, _("Passport expires %(date)s") % {"date": candidate.passport_expiry.strftime("%d %b %Y")}))
    else:
        got += 2
    if candidate.gulf_experience:
        got = min(got + 3, total)
        reasons.append((True, _("Gulf experience")))

    percent = round(100 * got / total) if total else 0
    return (0 if blocked else percent), reasons, blocked


def rank(job, candidates, today=None, limit=200):
    """Candidates with .match / .reasons set, best first; a blocked candidate goes to the end."""
    out = []
    for c in candidates:
        c.match, c.reasons, c.blocked = score(job, c, today)
        out.append(c)
    out.sort(key=lambda c: (c.blocked, -c.match, c.name.lower()))
    return out[:limit]


def jobs_for(candidate, jobs, today=None, limit=10):
    """Open jobs that fit this candidate, best first."""
    out = []
    for job in jobs:
        job.match, job.reasons, job.blocked = score(job, candidate, today)
        if not job.blocked and job.match >= 30:
            out.append(job)
    out.sort(key=lambda j: -j.match)
    return out[:limit]
