"""``register_account`` - public registration (User Story 3). Served only on ``/public/mcp``."""

from __future__ import annotations

import re
from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.tools import Tool
from pydantic import Field, field_validator

from ..api import users as api_users
from ..api.client import ApiClient
from .confirm import write_tool
from .models import WriteInput

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

NEXT_STEP = (
    "Check your inbox and open the verification link we sent to finish registration. Note: "
    "accounts created with a password cannot sign in through the assistant yet; the assistant's "
    "signed-in tools currently require signing in with Google."
)


def normalize_cpf(value: str) -> str:
    return re.sub(r"[.\-\s]", "", value)


def is_valid_cpf(value: str) -> bool:
    digits = normalize_cpf(value)
    if not re.fullmatch(r"\d{11}", digits) or len(set(digits)) == 1:
        return False
    numbers = [int(d) for d in digits]
    for size in (9, 10):
        total = sum(n * w for n, w in zip(numbers[:size], range(size + 1, 1, -1), strict=True))
        check = (total * 10) % 11 % 10
        if numbers[size] != check:
            return False
    return True


def mask_cpf(value: str) -> str:
    """Show only the last three digits: ``***.***.**7-25``."""
    digits = normalize_cpf(value)
    return f"***.***.**{digits[-3]}-{digits[-2:]}"


class RegisterAccountInput(WriteInput):
    name: str = Field(min_length=1, max_length=200, description="Full name")
    email: str = Field(max_length=254, description="Email address (a verification email is sent)")
    cpf: str = Field(description="Brazilian CPF, with or without punctuation")
    password: str = Field(
        min_length=8,
        max_length=200,
        description="Password (at least 8 characters). Sent only to the EntrePatasETurnos API.",
        json_schema_extra={"format": "password", "writeOnly": True},
    )

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if not _EMAIL_RE.match(value):
            raise ValueError("email is not a valid address")
        return value

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, value: str) -> str:
        if not is_valid_cpf(value):
            raise ValueError("cpf is not a valid CPF")
        return normalize_cpf(value)


def registration_summary(inp: RegisterAccountInput) -> dict[str, Any]:
    return {"name": inp.name, "email": inp.email, "CPF": mask_cpf(inp.cpf)}


def build_registration_tools(api: ApiClient) -> list[Tool]:
    async def register(inp: RegisterAccountInput, ctx: Context) -> dict[str, Any]:
        body = await api_users.register(
            api, email=inp.email, name=inp.name, cpf=inp.cpf, password=inp.password
        )
        body = body if isinstance(body, dict) else {}
        return {
            "email": body.get("email", inp.email),
            "status": body.get("status"),
            "next_step": NEXT_STEP,
        }

    return [
        write_tool(
            name="register_account",
            title="Register an account",
            description=(
                "Create a new EntrePatasETurnos account with name, email, CPF and password. The "
                "password is sent only to the EntrePatasETurnos API and is never shown back. Do not "
                "repeat the password to the user in the confirmation."
            ),
            input_model=RegisterAccountInput,
            summarize=registration_summary,
            action=register,
        )
    ]
