from decimal import Decimal
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import GenderEnum, RoleEnum, SubscriptionPlanType
from app.models.user import User


def _create_user_and_token(
    session: Session,
    identifier: str,
    role: RoleEnum,
    is_active: bool = True,
) -> tuple[User, str]:
    phone_digits = f"{abs(hash(identifier)) % 100000000:08d}"
    phone_number = f"+2010{phone_digits}"
    user = User(
        full_name=f"{role.value} Test",
        phone_number=phone_number,
        password_hash=hash_password("Password123!"),
        gender=GenderEnum.MALE,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def test_subscription_plans_api_crud_and_rbac(
    client_with_db: TestClient, db_session: Session
) -> None:
    ceo, ceo_token = _create_user_and_token(db_session, "ceo_plans@ra7al.edu", RoleEnum.CEO)
    student, student_token = _create_user_and_token(
        db_session, "student_plans@ra7al.edu", RoleEnum.STUDENT
    )

    ceo_headers = {"Authorization": f"Bearer {ceo_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Student cannot create plan
    res = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Illegal Plan", "plan_type": "MONTHLY", "duration_days": 30, "days_per_week": 4, "price": 500.0},
        headers=student_headers,
    )
    assert res.status_code == 403

    # 2. CEO creates DAILY, WEEKLY, MONTHLY, and TERM plans with CEO-defined durations
    res_daily = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Daily Plan", "plan_type": "DAILY", "duration_days": 1, "days_per_week": 1, "price": 45.0},
        headers=ceo_headers,
    )
    assert res_daily.status_code == 201
    daily_id = res_daily.json()["id"]
    assert res_daily.json()["duration_days"] == 1
    assert res_daily.json()["days_per_week"] == 1

    res_weekly = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Weekly Pass", "plan_type": "WEEKLY", "duration_days": 7, "days_per_week": 4, "price": 150.0},
        headers=ceo_headers,
    )
    assert res_weekly.status_code == 201
    weekly_id = res_weekly.json()["id"]
    assert res_weekly.json()["plan_type"] == "WEEKLY"
    assert res_weekly.json()["duration_days"] == 7
    assert res_weekly.json()["days_per_week"] == 4

    res_monthly = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Monthly Pass", "plan_type": "MONTHLY", "duration_days": 30, "days_per_week": 5, "price": 800.0},
        headers=ceo_headers,
    )
    assert res_monthly.status_code == 201
    monthly_id = res_monthly.json()["id"]
    assert res_monthly.json()["duration_days"] == 30
    assert res_monthly.json()["days_per_week"] == 5

    # A second monthly package with a different custom duration is allowed
    res_monthly_45 = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Monthly Extended", "plan_type": "MONTHLY", "duration_days": 45, "days_per_week": 5, "price": 950.0},
        headers=ceo_headers,
    )
    assert res_monthly_45.status_code == 201
    assert res_monthly_45.json()["duration_days"] == 45

    # Custom TERM duration is allowed
    res_term = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Term Pass", "plan_type": "TERM", "duration_days": 120, "days_per_week": 5, "price": 2200.0},
        headers=ceo_headers,
    )
    assert res_term.status_code == 201
    term_id = res_term.json()["id"]
    assert res_term.json()["duration_days"] == 120

    # duration_days = 0 is rejected
    res_zero = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Zero Plan", "plan_type": "MONTHLY", "duration_days": 0, "days_per_week": 4, "price": 100.0},
        headers=ceo_headers,
    )
    assert res_zero.status_code == 422

    # negative duration is rejected
    res_neg = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Negative Plan", "plan_type": "TERM", "duration_days": -5, "days_per_week": 4, "price": 100.0},
        headers=ceo_headers,
    )
    assert res_neg.status_code == 422

    # days_per_week = 0 is rejected
    res_dpw_zero = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "No Usage Plan", "plan_type": "MONTHLY", "duration_days": 30, "days_per_week": 0, "price": 100.0},
        headers=ceo_headers,
    )
    assert res_dpw_zero.status_code == 422

    # days_per_week = 8 is rejected (a week has only 7 days)
    res_dpw_eight = client_with_db.post(
        "/api/v1/subscription-plans",
        json={"name": "Eight Week Plan", "plan_type": "MONTHLY", "duration_days": 30, "days_per_week": 8, "price": 100.0},
        headers=ceo_headers,
    )
    assert res_dpw_eight.status_code == 422

    # 3. Student views available plans
    res_student_list = client_with_db.get(
        "/api/v1/subscription-plans",
        headers=student_headers,
    )
    assert res_student_list.status_code == 200
    assert res_student_list.json()["total"] == 5

    # Student alias endpoint
    res_alias = client_with_db.get(
        "/api/v1/subscriptions/plans",
        headers=student_headers,
    )
    assert res_alias.status_code == 200
    assert len(res_alias.json()) == 5

    # 4. CEO updates plan price and weekly allowance
    res_update = client_with_db.patch(
        f"/api/v1/subscription-plans/{daily_id}",
        json={"price": 50.0, "days_per_week": 1},
        headers=ceo_headers,
    )
    assert res_update.status_code == 200
    assert float(res_update.json()["price"]) == 50.0
    assert res_update.json()["days_per_week"] == 1

    # 5. CEO deactivates a plan
    res_deactivate = client_with_db.patch(
        f"/api/v1/subscription-plans/{term_id}/status",
        json={"is_active": False},
        headers=ceo_headers,
    )
    assert res_deactivate.status_code == 200
    assert res_deactivate.json()["is_active"] is False

    # 6. Student now sees only 4 active plans
    res_student_after = client_with_db.get(
        "/api/v1/subscription-plans",
        headers=student_headers,
    )
    assert res_student_after.json()["total"] == 4
