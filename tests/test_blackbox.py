"""Black-box test suite for the Student Course Registration System.

Expected results are derived ONLY from REQUIREMENTS.md (the SRS).
Each test uses freshly constructed Student / Course objects via factory
functions, so no state leaks between tests.

Test IDs carry every technique tag they consolidate:
    ECP   — Equivalence Class Partitioning
    BVA   — Boundary Value Analysis
    DT    — Decision Table
    VO    — Validation Order (FR-02, FR-15)
    NM    — Non-Mutation (FR-10)
    SC    — State Change (FR-11..FR-14)
"""
import copy

import pytest

from registration import (
    Student,
    Course,
    check_credit_limit,
    prerequisites_satisfied,
    registration_decision,
    register_course,
    withdraw_course,
)


# ---------------------------------------------------------------------------
# Factories — one fresh object per test (no shared fixture state)
# ---------------------------------------------------------------------------
def make_student(
    student_id: str = "S1",
    completed_courses=None,
    current_credits: int = 0,
    outstanding_dues: int = 0,
    registered_courses=None,
) -> Student:
    return Student(
        student_id=student_id,
        completed_courses=set(completed_courses) if completed_courses else set(),
        current_credits=current_credits,
        outstanding_dues=outstanding_dues,
        registered_courses=set(registered_courses) if registered_courses else set(),
    )


def make_course(
    code: str = "C1",
    credit_hours: int = 3,
    capacity: int = 10,
    enrolled: int = 0,
    prerequisites=None,
    waitlist=None,
) -> Course:
    return Course(
        code=code,
        credit_hours=credit_hours,
        capacity=capacity,
        enrolled=enrolled,
        prerequisites=set(prerequisites) if prerequisites else set(),
        waitlist=list(waitlist) if waitlist else [],
    )


# ===========================================================================
# FR-01 / FR-02 — check_credit_limit — returns
# ===========================================================================
@pytest.mark.parametrize(
    "current, new, expected, tag",
    [
        (10, 3, True, "ECP-01"),
        (17, 1, True, "BVA-03"),
        (18, 1, False, "BVA-04"),
        (10, 1, True, "BVA-07"),
        (10, 4, True, "BVA-08"),
        (0, 1, True, "BVA-17"),
        (14, 4, True, "BVA-18"),
        (15, 4, False, "BVA-19"),
    ],
    ids=[
        "ECP-01_valid_10+3",
        "BVA-03_exactly_18_allowed",
        "BVA-04_just_over_19",
        "BVA-07_min_new_1",
        "BVA-08_max_new_4",
        "BVA-17_zero_plus_one",
        "BVA-18_fourteen_plus_four",
        "BVA-19_fifteen_plus_four",
    ],
)
def test_check_credit_limit_returns(current, new, expected, tag):
    """FR-01: current + new <= 18 -> True, otherwise False."""
    assert check_credit_limit(current, new) is expected, tag


# ===========================================================================
# FR-02 / FR-15 — check_credit_limit — raises (validation order VO-01, VO-02)
# ===========================================================================
@pytest.mark.parametrize(
    "current, new, msg, tag",
    [
        (-1, 3, "Invalid current credits", "ECP-02__BVA-01"),
        (19, 3, "Invalid current credits", "BVA-02"),
        (10, 5, "Invalid course credits", "ECP-03__BVA-06"),
        (10, 0, "Invalid course credits", "BVA-05"),
        (-1, 5, "Invalid current credits", "VO-01"),
        (20, 5, "Invalid current credits", "VO-02"),
    ],
    ids=[
        "ECP-02__BVA-01_current_minus1",
        "BVA-02_current_19",
        "ECP-03__BVA-06_new_5",
        "BVA-05_new_0",
        "VO-01_both_invalid_current_first",
        "VO-02_upper_current_before_new",
    ],
)
def test_check_credit_limit_raises(current, new, msg, tag):
    """FR-02: ValueError with exact SRS message; current checked before new."""
    with pytest.raises(ValueError) as exc:
        check_credit_limit(current, new)
    assert str(exc.value) == msg, tag


# ===========================================================================
# FR-03 — prerequisites_satisfied (ECP-04, ECP-05, ECP-06)
# ===========================================================================
@pytest.mark.parametrize(
    "completed, required, expected, tag",
    [
        (set(), set(), True, "ECP-04"),
        ({"CS101"}, {"CS101"}, True, "ECP-05"),
        ({"CS101"}, {"CS101", "MATH101"}, False, "ECP-06"),
    ],
    ids=[
        "ECP-04_no_required",
        "ECP-05_single_met",
        "ECP-06_partial_missing",
    ],
)
def test_prerequisites_satisfied(completed, required, expected, tag):
    """FR-03: True iff every required course is completed; empty -> True."""
    assert prerequisites_satisfied(completed, required) is expected, tag


# ===========================================================================
# FR-04..FR-09 — registration_decision — statuses
# (ECP + BVA + DT including priority-conflict rows and DT-11/12/13)
# ===========================================================================
@pytest.mark.parametrize(
    "student, course, expected, tag",
    [
        (make_student(outstanding_dues=1), make_course(enrolled=0),
         "DUES_BLOCK", "ECP-07__BVA-11__DT-01"),
        (make_student(outstanding_dues=0), make_course(enrolled=0),
         "REGISTERED", "BVA-10__BVA-22"),
        (make_student(registered_courses={"C1"}), make_course(enrolled=0),
         "ALREADY_REGISTERED", "ECP-09__DT-02"),
        (make_student(), make_course(enrolled=0, prerequisites={"CS101"}),
         "PREREQUISITES_MISSING", "ECP-13__DT-03"),
        (make_student(completed_courses={"CS101"}),
         make_course(enrolled=0, prerequisites={"CS101", "MATH101"}),
         "PREREQUISITES_MISSING", "DT-12"),
        (make_student(current_credits=16), make_course(enrolled=0),
         "CREDIT_LIMIT", "ECP-14__DT-04"),
        (make_student(), make_course(capacity=10, enrolled=10),
         "WAITLISTED", "ECP-10__BVA-16__DT-05"),
        (make_student(), make_course(capacity=10, enrolled=9),
         "REGISTERED", "ECP-11__BVA-15__DT-06"),
        (make_student(), make_course(capacity=1, enrolled=0),
         "REGISTERED", "BVA-20"),
        (make_student(), make_course(capacity=1, enrolled=1),
         "WAITLISTED", "BVA-21"),
        (make_student(current_credits=15), make_course(enrolled=0),
         "REGISTERED", "DT-11"),
        (make_student(completed_courses={"CS101", "MATH101"}),
         make_course(enrolled=0, prerequisites={"CS101", "MATH101"}),
         "REGISTERED", "DT-13"),
        (make_student(outstanding_dues=1, registered_courses={"C1"}),
         make_course(enrolled=0),
         "DUES_BLOCK", "DT-07"),
        (make_student(registered_courses={"C1"}),
         make_course(enrolled=0, prerequisites={"CS101"}),
         "ALREADY_REGISTERED", "DT-08"),
        (make_student(current_credits=16),
         make_course(enrolled=0, prerequisites={"CS101"}),
         "PREREQUISITES_MISSING", "DT-09"),
        (make_student(current_credits=16),
         make_course(capacity=10, enrolled=10),
         "CREDIT_LIMIT", "DT-10"),
    ],
    ids=[
        "ECP-07__BVA-11__DT-01_dues_blocks",
        "BVA-10__BVA-22_zero_dues_register",
        "ECP-09__DT-02_already_registered",
        "ECP-13__DT-03_missing_prereq",
        "DT-12_partial_prereq_missing",
        "ECP-14__DT-04_credit_limit",
        "ECP-10__BVA-16__DT-05_waitlisted",
        "ECP-11__BVA-15__DT-06_registered",
        "BVA-20_capacity1_enrolled0",
        "BVA-21_capacity1_enrolled1",
        "DT-11_fifteen_plus_three_registered",
        "DT-13_all_prereqs_met",
        "DT-07_dues_and_dup",
        "DT-08_dup_and_missing_prereq",
        "DT-09_prereq_and_credit",
        "DT-10_credit_and_full",
    ],
)
def test_registration_decision_status(student, course, expected, tag):
    """FR-04..FR-09: decision statuses, priority order, and BVA boundaries."""
    assert registration_decision(student, course) == expected, tag


# ===========================================================================
# FR-15 — registration_decision — raises (includes validation-order VO-03/04)
# ===========================================================================
@pytest.mark.parametrize(
    "student, course, msg, tag",
    [
        (make_student(outstanding_dues=-1), make_course(capacity=10, enrolled=0),
         "Invalid dues", "ECP-08__BVA-09"),
        (make_student(), make_course(capacity=0, enrolled=0),
         "Invalid capacity or enrollment", "ECP-12__BVA-12"),
        (make_student(), make_course(capacity=10, enrolled=-1),
         "Invalid capacity or enrollment", "BVA-13"),
        (make_student(), make_course(capacity=10, enrolled=11),
         "Invalid capacity or enrollment", "BVA-14"),
        (make_student(outstanding_dues=-1), make_course(capacity=0, enrolled=0),
         "Invalid dues", "VO-03"),
        (make_student(outstanding_dues=-1), make_course(capacity=10, enrolled=15),
         "Invalid dues", "VO-04"),
    ],
    ids=[
        "ECP-08__BVA-09_negative_dues",
        "ECP-12__BVA-12_capacity_zero",
        "BVA-13_enrolled_minus1",
        "BVA-14_enrolled_cap_plus1",
        "VO-03_dues_before_capacity",
        "VO-04_dues_before_enrollment",
    ],
)
def test_registration_decision_raises(student, course, msg, tag):
    """FR-15: exact SRS messages; dues validated before capacity/enrollment."""
    with pytest.raises(ValueError) as exc:
        registration_decision(student, course)
    assert str(exc.value) == msg, tag


# ===========================================================================
# FR-10 — registration_decision does not mutate (NM-01..NM-06)
# ===========================================================================
@pytest.mark.parametrize(
    "student, course, tag",
    [
        (make_student(outstanding_dues=0, current_credits=0),
         make_course(enrolled=0), "NM-01"),
        (make_student(), make_course(capacity=10, enrolled=10), "NM-02"),
        (make_student(outstanding_dues=1), make_course(enrolled=0), "NM-03"),
        (make_student(registered_courses={"C1"}), make_course(enrolled=0), "NM-04"),
        (make_student(), make_course(enrolled=0, prerequisites={"CS101"}), "NM-05"),
        (make_student(current_credits=16), make_course(enrolled=0), "NM-06"),
    ],
    ids=[
        "NM-01_registered_path",
        "NM-02_waitlisted_path",
        "NM-03_dues_path",
        "NM-04_already_path",
        "NM-05_prereq_path",
        "NM-06_credit_path",
    ],
)
def test_registration_decision_no_mutation(student, course, tag):
    """FR-10: registration_decision must not modify student or course."""
    student_before = copy.deepcopy(student)
    course_before = copy.deepcopy(course)
    registration_decision(student, course)
    assert student == student_before, tag
    assert course == course_before, tag


# ===========================================================================
# FR-11 / FR-12 — register_course state changes
# ===========================================================================
def test_register_course_SC01_registered_state():
    """SC-01 (FR-11): REGISTERED adds course, adds credits, increments enrolled."""
    s = make_student(current_credits=0)
    c = make_course(credit_hours=3, capacity=10, enrolled=0)
    result = register_course(s, c)
    assert result == "REGISTERED", "SC-01"
    assert s.registered_courses == {"C1"}, "SC-01"
    assert s.current_credits == 3, "SC-01"
    assert c.enrolled == 1, "SC-01"


def test_register_course_SC02_waitlisted_state():
    """SC-02 (FR-12): WAITLISTED appends ID, no other state change."""
    s = make_student(current_credits=0)
    c = make_course(credit_hours=3, capacity=10, enrolled=10, waitlist=[])
    result = register_course(s, c)
    assert result == "WAITLISTED", "SC-02"
    assert s.registered_courses == set(), "SC-02"
    assert s.current_credits == 0, "SC-02"
    assert c.enrolled == 10, "SC-02"
    assert c.waitlist == ["S1"], "SC-02"


def test_register_course_SC03_waitlist_no_duplicate():
    """SC-03 (FR-12): already in waitlist -> do not append again."""
    s = make_student(student_id="S1")
    c = make_course(credit_hours=3, capacity=10, enrolled=10, waitlist=["S1"])
    result = register_course(s, c)
    assert result == "WAITLISTED", "SC-03"
    assert c.waitlist == ["S1"], "SC-03"


@pytest.mark.parametrize(
    "student, course, expected_decision, tag",
    [
        (make_student(outstanding_dues=1), make_course(enrolled=0),
         "DUES_BLOCK", "SC-04"),
        (make_student(registered_courses={"C1"}), make_course(enrolled=0),
         "ALREADY_REGISTERED", "SC-05"),
        (make_student(), make_course(enrolled=0, prerequisites={"CS101"}),
         "PREREQUISITES_MISSING", "SC-06"),
        (make_student(current_credits=16), make_course(enrolled=0),
         "CREDIT_LIMIT", "SC-07"),
    ],
    ids=[
        "SC-04_dues_block_unchanged",
        "SC-05_already_unchanged",
        "SC-06_prereq_unchanged",
        "SC-07_credit_unchanged",
    ],
)
def test_register_course_unsuccessful_no_state_change(student, course, expected_decision, tag):
    """FR-12: unsuccessful operations make no state changes."""
    student_before = copy.deepcopy(student)
    course_before = copy.deepcopy(course)
    result = register_course(student, course)
    assert result == expected_decision, tag
    assert student == student_before, tag
    assert course == course_before, tag


def test_register_course_SC10_exactly_eighteen_credits():
    """SC-10 (FR-11): 15 + 3 = 18 must succeed with the full post-state."""
    s = make_student(current_credits=15)
    c = make_course(credit_hours=3, capacity=10, enrolled=0)
    result = register_course(s, c)
    assert result == "REGISTERED", "SC-10"
    assert s.registered_courses == {"C1"}, "SC-10"
    assert s.current_credits == 18, "SC-10"
    assert c.enrolled == 1, "SC-10"


# ===========================================================================
# FR-13 / FR-14 — withdraw_course state changes
# ===========================================================================
def test_withdraw_course_SC08_enrolled():
    """SC-08 (FR-13): enrolled student is removed, credits drop, enrolled-1."""
    s = make_student(registered_courses={"C1"}, current_credits=3)
    c = make_course(credit_hours=3, capacity=10, enrolled=1)
    result = withdraw_course(s, c)
    assert result is True, "SC-08"
    assert s.registered_courses == set(), "SC-08"
    assert s.current_credits == 0, "SC-08"
    assert c.enrolled == 0, "SC-08"


def test_withdraw_course_SC09_not_enrolled():
    """SC-09 (FR-14): not enrolled -> False and no state change."""
    s = make_student()
    c = make_course(credit_hours=3, capacity=10, enrolled=0)
    s_before = copy.deepcopy(s)
    c_before = copy.deepcopy(c)
    result = withdraw_course(s, c)
    assert result is False, "SC-09"
    assert s == s_before, "SC-09"
    assert c == c_before, "SC-09"
