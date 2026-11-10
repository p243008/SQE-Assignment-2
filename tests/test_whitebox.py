"""White-box test suite for registration_decision / register_course / withdraw_course.

Each test documents the exact CFG path, branch, or condition it targets.
Expected outcomes come from REQUIREMENTS.md — never from observing
registration.py's actual behaviour.

Companion to tests/test_blackbox.py. Together these close the three baseline
coverage gaps:
  * line 51 (DUES_BLOCK)     — covered here by WB-P5
  * lines 59 and 71 (waitlist) — dead under D4; documented in WB-P9 / WB-RC2
"""
import pytest

from registration import (
    Student,
    Course,
    registration_decision,
    register_course,
    withdraw_course,
)


# ---------------------------------------------------------------------------
# Factories — fresh objects per test, no shared state.
# ---------------------------------------------------------------------------
def make_student(**kw):
    defaults = dict(
        student_id="S1",
        completed_courses=set(),
        current_credits=0,
        outstanding_dues=0,
        registered_courses=set(),
    )
    defaults.update(kw)
    return Student(**defaults)


def make_course(**kw):
    defaults = dict(
        code="C1",
        credit_hours=3,
        capacity=10,
        enrolled=0,
        prerequisites=set(),
        waitlist=[],
    )
    defaults.update(kw)
    return Course(**defaults)


# ===========================================================================
# Basis paths of registration_decision (predicate-node V(G) = 10).
# ===========================================================================
class TestBasisPaths:
    """One representative test per basis path P1..P10."""

    def test_WB_P1_dues_negative(self):
        """P1: N2(T) -> N3 -> exit. Targets the dues<0 branch (line 45)."""
        with pytest.raises(ValueError) as exc:
            registration_decision(
                make_student(outstanding_dues=-1),
                make_course(capacity=10, enrolled=0),
            )
        assert str(exc.value) == "Invalid dues"

    def test_WB_P2_enrolled_negative_A_false(self):
        """P2: A False -> P_R -> exit (B and C short-circuited).
        Targets line 47's A-false outgoing edge."""
        with pytest.raises(ValueError) as exc:
            registration_decision(
                make_student(),
                make_course(enrolled=-1, capacity=10),
            )
        assert str(exc.value) == "Invalid capacity or enrollment"

    def test_WB_P3_enrolled_above_capacity_A_true_B_false(self):
        """P3: A True, B False -> P_R (C short-circuited).
        Targets line 47's B-false outgoing edge."""
        with pytest.raises(ValueError) as exc:
            registration_decision(
                make_student(),
                make_course(enrolled=15, capacity=10),
            )
        assert str(exc.value) == "Invalid capacity or enrollment"

    def test_WB_P4_capacity_zero_all_conditions_true(self):
        """P4: A True, B True, C True -> P_R.
        Targets line 47's C-true outgoing edge."""
        with pytest.raises(ValueError) as exc:
            registration_decision(
                make_student(),
                make_course(enrolled=0, capacity=0),
            )
        assert str(exc.value) == "Invalid capacity or enrollment"

    def test_WB_P5_dues_above_1000_covers_line51(self):
        """P5: N6(T) -> N7 -> exit. This is the ONLY white-box test that
        reaches line 51 (return 'DUES_BLOCK') under current code.
        Closes the coverage gap on line 51."""
        s = make_student(outstanding_dues=1001)
        c = make_course(capacity=10, enrolled=0)
        assert registration_decision(s, c) == "DUES_BLOCK"

    def test_WB_P6_already_registered(self):
        """P6: N8(T) -> N9 -> exit. Targets the already-registered branch."""
        assert registration_decision(
            make_student(registered_courses={"C1"}),
            make_course(capacity=10, enrolled=0),
        ) == "ALREADY_REGISTERED"

    def test_WB_P7_prerequisites_missing(self):
        """P7: N10(T) -> N11 -> exit. Targets the prerequisite branch."""
        assert registration_decision(
            make_student(),
            make_course(capacity=10, enrolled=0, prerequisites={"CS101"}),
        ) == "PREREQUISITES_MISSING"

    def test_WB_P8_credit_limit(self):
        """P8: N12(T) -> N13 -> exit. Targets the credit-limit branch."""
        assert registration_decision(
            make_student(current_credits=16),
            make_course(credit_hours=3, capacity=10, enrolled=0),
        ) == "CREDIT_LIMIT"

    @pytest.mark.skip(
        reason="P9 is a semantically dead path under D4 — the waitlist "
               "branch (N14->N15) is unreachable because line 48 already "
               "raises for enrolled > capacity. Black-box ECP-10 / BVA-16 / "
               "DT-05 exercise this path once D4 is fixed."
    )
    def test_WB_P9_waitlisted_dead_under_D4(self):
        """P9 (documented, not asserted): would require enrolled > capacity."""
        pass

    def test_WB_P10_registered(self):
        """P10: N14(F) -> N16 -> exit. Targets the normal registration path."""
        assert registration_decision(
            make_student(),
            make_course(capacity=10, enrolled=9),
        ) == "REGISTERED"


# ===========================================================================
# MC/DC for the compound validation on line 47:
#   not (0 <= enrolled <= capacity) or (capacity < 1)
# Atomic: A = 0<=enrolled, B = enrolled<=capacity, C = capacity<1.
# Short-circuit: B NE if A False; C NE unless A and B both True.
# ===========================================================================
class TestMCDCCompoundValidation:
    """Four tests establishing MC/DC independence of A, B, C."""

    def test_WB_MC1_A_T_B_T_C_F_pass(self):
        """Reference row: A=T, B=T, C=F -> no raise (pass to downstream)."""
        result = registration_decision(
            make_student(),
            make_course(enrolled=5, capacity=10),
        )
        assert result == "REGISTERED"

    def test_WB_MC2_A_F_short_circuit(self):
        """Independence pair for A: A=F -> B,C short-circuit -> raise."""
        with pytest.raises(ValueError) as exc:
            registration_decision(
                make_student(),
                make_course(enrolled=-1, capacity=10),
            )
        assert str(exc.value) == "Invalid capacity or enrollment"

    def test_WB_MC3_A_T_B_F_short_circuit(self):
        """Independence pair for B: A=T, B=F -> C short-circuits -> raise."""
        with pytest.raises(ValueError) as exc:
            registration_decision(
                make_student(),
                make_course(enrolled=15, capacity=10),
            )
        assert str(exc.value) == "Invalid capacity or enrollment"

    def test_WB_MC4_A_T_B_T_C_T_raise(self):
        """Independence pair for C: A=T, B=T, C=T -> raise."""
        with pytest.raises(ValueError) as exc:
            registration_decision(
                make_student(),
                make_course(enrolled=0, capacity=0),
            )
        assert str(exc.value) == "Invalid capacity or enrollment"


# ===========================================================================
# register_course — targeted branches.
# ===========================================================================
class TestRegisterCourseBranches:

    def test_WB_RC1_registered_branch_mutates(self):
        """Branch: decision == 'REGISTERED' -> all three mutations execute
        (lines 66-69). Confirms add-to-set / add-to-credits / increment."""
        s = make_student(current_credits=0)
        c = make_course(credit_hours=3, capacity=10, enrolled=0)
        assert register_course(s, c) == "REGISTERED"
        assert s.registered_courses == {"C1"}
        assert s.current_credits == 3
        assert c.enrolled == 1

    @pytest.mark.skip(
        reason="register_course waitlist branch (lines 70-71) is dead under "
               "D4 — the WAITLISTED decision is never returned. Black-box "
               "SC-02/SC-03 exercise this path once D4 is fixed."
    )
    def test_WB_RC2_waitlisted_branch_dead_under_D4(self):
        """Branch: decision == 'WAITLISTED' (documented, not asserted)."""
        pass

    def test_WB_RC3_other_decision_no_mutation(self):
        """Branch: decision neither REGISTERED nor WAITLISTED -> no mutation.
        Targets the implicit else of lines 63-71."""
        s = make_student(registered_courses={"C1"}, current_credits=0)
        c = make_course(credit_hours=3, capacity=10, enrolled=0)
        before_s = (s.completed_courses.copy(), s.current_credits,
                    s.registered_courses.copy())
        before_c = (c.enrolled, c.waitlist.copy())
        assert register_course(s, c) == "ALREADY_REGISTERED"
        assert (s.completed_courses, s.current_credits,
                s.registered_courses) == before_s
        assert (c.enrolled, c.waitlist) == before_c


# ===========================================================================
# withdraw_course — targeted branches.
# ===========================================================================
class TestWithdrawCourseBranches:

    def test_WB_WC1_true_branch(self):
        """Branch: enrolled -> True (lines 79-81)."""
        s = make_student(registered_courses={"C1"}, current_credits=3)
        c = make_course(credit_hours=3, capacity=10, enrolled=1)
        assert withdraw_course(s, c) is True
        assert s.registered_courses == set()
        assert s.current_credits == 0

    def test_WB_WC2_false_branch(self):
        """Branch: not enrolled -> False (line 78). No mutation."""
        s = make_student()
        c = make_course(capacity=10, enrolled=0)
        before_s = (s.completed_courses.copy(), s.current_credits,
                    s.registered_courses.copy())
        before_c = (c.enrolled, c.waitlist.copy())
        assert withdraw_course(s, c) is False
        assert (s.completed_courses, s.current_credits,
                s.registered_courses) == before_s
        assert (c.enrolled, c.waitlist) == before_c
