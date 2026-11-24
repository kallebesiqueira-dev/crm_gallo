"""Seed the public demo tenant.

Login (also printed at the end of a successful run):
  email:    demo@gallo-crm.dev
  password: Gallo-Demo-2026!

Idempotent: if that user already exists, the script leaves the database
alone and exits 0.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal, set_current_org_id
from app.models import (
    BillingCycle,
    Company,
    Currency,
    Customer,
    Deal,
    DealStage,
    Lead,
    LeadStage,
    NextActionType,
    Note,
    Organization,
    OrgMembership,
    Plan,
    Task,
    TaskPriority,
    TaskStatus,
    User,
    UserRole,
)
from app.security import hash_password

DEMO_EMAIL = "demo@gallo-crm.dev"
DEMO_PASSWORD = "Gallo-Demo-2026!"
DEMO_NAME = "Mara Keller"


async def seed() -> None:
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"demo user already present: {DEMO_EMAIL}")
            return

        org = Organization(
            name="Atelier Nord",
            slug="atelier-nord",
            plan=Plan.premium,
            billing_cycle=BillingCycle.yearly,
            default_currency=Currency.EUR,
            plan_started_at=datetime.now(UTC),
        )
        db.add(org)
        await db.flush()

        user = User(
            email=DEMO_EMAIL,
            full_name=DEMO_NAME,
            hashed_password=hash_password(DEMO_PASSWORD),
            role=UserRole.admin,
            locale="en",
            display_currency=Currency.EUR,
            is_active=True,
            email_verified=True,
            mfa_enabled=False,
            last_active_org_id=org.id,
        )
        db.add(user)
        await db.flush()
        db.add(
            OrgMembership(
                user_id=user.id,
                organization_id=org.id,
                role=UserRole.admin,
            )
        )
        await db.commit()
        # The RLS GUC is applied when a transaction begins. Commit first so
        # the rows below open a fresh transaction that can see this org.
        set_current_org_id(org.id)
        org_id = org.id
        user_id = user.id

        companies = [
            Company(
                organization_id=org_id,
                name="Helvetia Glass",
                industry="Manufacturing",
                website="https://helvetia-glass.example",
                country="CH",
                size=120,
                email="hello@helvetia-glass.example",
                owner_id=user_id,
            ),
            Company(
                organization_id=org_id,
                name="Lumen Studio",
                industry="Design",
                website="https://lumen.example",
                country="IT",
                size=18,
                email="studio@lumen.example",
                owner_id=user_id,
            ),
            Company(
                organization_id=org_id,
                name="Porto & Co",
                industry="Hospitality",
                website="https://portoandco.example",
                country="PT",
                size=40,
                email="events@portoandco.example",
                owner_id=user_id,
            ),
            Company(
                organization_id=org_id,
                name="Brava Retail",
                industry="Retail",
                website="https://brava.example",
                country="ES",
                size=75,
                email="buyers@brava.example",
                owner_id=user_id,
            ),
        ]
        db.add_all(companies)
        await db.flush()

        people = [
            ("Elena", "Vogel", "elena.vogel@helvetia-glass.example", companies[0], "CH"),
            ("Luca", "Bianchi", "luca.bianchi@lumen.example", companies[1], "IT"),
            ("Inês", "Costa", "ines.costa@portoandco.example", companies[2], "PT"),
            ("Sofia", "Navarro", "sofia.navarro@brava.example", companies[3], "ES"),
            ("Jonas", "Meier", "jonas.meier@helvetia-glass.example", companies[0], "CH"),
            ("Chloé", "Martin", "chloe.martin@lumen.example", companies[1], "FR"),
        ]
        customers = []
        for first, last, email, company, country in people:
            customer = Customer(
                organization_id=org_id,
                first_name=first,
                last_name=last,
                email=email,
                company=company.name,
                company_id=company.id,
                country=country,
                owner_id=user_id,
            )
            customers.append(customer)
        db.add_all(customers)
        await db.flush()

        leads = [
            ("Nora", "Keller", "nora.keller@feld.example", "Feld Logistics", LeadStage.new, "DE"),
            ("Hugo", "Pereira", "hugo@ribeira.example", "Ribeira Foods", LeadStage.contacted, "PT"),
            ("Amina", "Diallo", "amina@sahel.example", "Sahel Solar", LeadStage.qualified, "FR"),
            (
                "Theo",
                "Keller",
                "theo@alpen.example",
                "Alpen Mobility",
                LeadStage.proposal_sent,
                "CH",
            ),
        ]
        for first, last, email, company, stage, country in leads:
            db.add(
                Lead(
                    organization_id=org_id,
                    first_name=first,
                    last_name=last,
                    email=email,
                    company=company,
                    country=country,
                    stage=stage,
                    source="demo",
                    owner_id=user_id,
                    ai_score=62,
                )
            )

        today = date.today()
        # title, amount, stage, customer index, days until close, next action
        deal_rows = [
            ("Showroom fit-out", "48000", DealStage.qualified, 1, 7, NextActionType.meeting),
            ("Menu glassware", "18600", DealStage.proposal_sent, 2, 3, NextActionType.proposal),
            ("Flagship lighting", "92000", DealStage.negotiation, 0, 1, NextActionType.call),
            ("Summer terrace", "12400", DealStage.new, 3, 14, NextActionType.email),
            ("Hotel relaunch", "64000", DealStage.won, 2, -10, None),
            ("Pop-up Milan", "21000", DealStage.lost, 1, -20, None),
            ("Window campaign", "27500", DealStage.negotiation, 3, 0, NextActionType.chase),
            ("Retainers", "36000", DealStage.qualified, 0, 21, NextActionType.follow_up),
        ]
        deals = []
        for index, (title, amount, stage, who, close_in, action) in enumerate(deal_rows):
            value = Decimal(amount)
            customer = customers[who]
            action_at = None
            if action is not None:
                action_at = datetime.now(UTC) + timedelta(days=close_in if close_in < 3 else 1)
                if title == "Window campaign":
                    action_at = datetime.now(UTC) - timedelta(hours=6)
            deal = Deal(
                organization_id=org_id,
                title=title,
                value=value,
                currency=Currency.EUR,
                stage=stage,
                probability=70 if stage == DealStage.negotiation else 30,
                expected_close_date=today + timedelta(days=close_in),
                customer_id=customer.id,
                company_id=customer.company_id,
                owner_id=user_id,
                sort_index=index,
                next_action_type=action,
                next_action_at=action_at,
            )
            deals.append(deal)
        db.add_all(deals)
        await db.flush()

        db.add_all(
            [
                Task(
                    organization_id=org_id,
                    title="Call Elena about the flagship timeline",
                    status=TaskStatus.todo,
                    priority=TaskPriority.high,
                    due_date=today,
                    assignee_id=user_id,
                    customer_id=customers[0].id,
                    deal_id=deals[2].id,
                ),
                Task(
                    organization_id=org_id,
                    title="Send revised quote to Porto & Co",
                    status=TaskStatus.in_progress,
                    priority=TaskPriority.high,
                    due_date=today + timedelta(days=1),
                    assignee_id=user_id,
                    customer_id=customers[2].id,
                    deal_id=deals[1].id,
                ),
                Task(
                    organization_id=org_id,
                    title="Log the Milan pop-up loss reason",
                    status=TaskStatus.todo,
                    priority=TaskPriority.medium,
                    due_date=today - timedelta(days=1),
                    assignee_id=user_id,
                    deal_id=deals[5].id,
                ),
                Task(
                    organization_id=org_id,
                    title="Intro Brava buyers to the terrace line",
                    status=TaskStatus.todo,
                    priority=TaskPriority.low,
                    due_date=today + timedelta(days=5),
                    assignee_id=user_id,
                    customer_id=customers[3].id,
                ),
            ]
        )
        db.add_all(
            [
                Note(
                    organization_id=org_id,
                    author_user_id=user_id,
                    entity_type="deal",
                    entity_id=deals[2].id,
                    body=(
                        "Elena wants the lighting spec locked before "
                        "the Zurich site visit on Thursday."
                    ),
                ),
                Note(
                    organization_id=org_id,
                    author_user_id=user_id,
                    entity_type="customer",
                    entity_id=customers[2].id,
                    body="Inês prefers WhatsApp for day-of event changes and email for contracts.",
                ),
                Note(
                    organization_id=org_id,
                    author_user_id=user_id,
                    entity_type="deal",
                    entity_id=deals[1].id,
                    body="Quote v2 drops the custom etching. Margin stays above 32%.",
                ),
            ]
        )
        await db.commit()
        print(f"seeded {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
